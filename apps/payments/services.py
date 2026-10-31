"""Payment flow shared by everything the site sells (PAY-1, spec section 8.2).

Rules from the spec:
- callback parameters are never trusted: the server always calls `verify`
- the verified amount must match the order
- a repeated callback or page refresh changes nothing (idempotent)
- open payments are re-checked, for customers who closed the page after paying
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.content.models import SiteSettings
from apps.notifications.services import send_email
from apps.orders import services as orders
from apps.orders.models import Order

from .gateways import GatewayError, get_gateway
from .models import Payment

logger = logging.getLogger(__name__)

# The customer may still be on the bank page until this much time has passed
RECONCILE_AFTER = timedelta(minutes=20)
RECONCILE_UNTIL = timedelta(days=1)


class PaymentUnavailable(Exception):
    """No gateway accepted the request; the customer can try again."""


def start_payment(order: Order, callback_url_for) -> str:
    """Create a payment and return the bank URL. Tries each configured gateway in order.

    `callback_url_for(gateway_name)` builds the absolute callback URL.
    """
    if not order.can_pay:
        raise PaymentUnavailable("order is not payable")

    for name in settings.PAYMENT_GATEWAY_ORDER:
        payment = Payment.objects.create(order=order, gateway=name, amount=order.total)
        try:
            issued = get_gateway(name).request(
                order.total,
                callback_url_for(name),
                f"سفارش {order.number}",
                mobile=order.user.mobile,
                order_id=order.number,
            )
        except GatewayError as exc:
            logger.warning("gateway %s failed for order %s: %s", name, order.number, exc)
            payment.status = Payment.Status.FAILED
            payment.raw_response = {"error": str(exc)[:500]}
            payment.save(update_fields=["status", "raw_response"])
            continue
        payment.authority = issued.authority
        payment.save(update_fields=["authority"])
        return issued.redirect_url
    raise PaymentUnavailable("no gateway available")


def settle(payment_id: int) -> Payment:
    """Ask the gateway for the truth about a payment and apply it, once.

    The row lock makes a second callback wait, then return without calling the
    gateway again. If the gateway is unreachable the payment stays open and
    `reconcile` finishes it later.
    """
    with transaction.atomic():
        payment = (
            Payment.objects.select_for_update(of=("self",))
            .select_related("order")
            .get(pk=payment_id)
        )
        if payment.status != Payment.Status.INITIATED:
            return payment
        try:
            result = get_gateway(payment.gateway).verify(payment.authority, payment.amount)
        except GatewayError as exc:
            logger.warning("verify failed for payment %s: %s", payment.pk, exc)
            return payment

        payment.raw_response = result.raw
        payment.verified_at = timezone.now()
        amount_ok = result.amount is None or result.amount == payment.amount
        if result.ok and amount_ok:
            payment.status = Payment.Status.PAID
            payment.ref_id = result.ref_id
            payment.card_mask = result.card_mask
        else:
            payment.status = Payment.Status.FAILED
        payment.save()

        order = Order.objects.select_for_update().get(pk=payment.order_id)
        first_payment = payment.status == Payment.Status.PAID and orders.mark_paid(order)

    if result.ok and not amount_ok:
        logger.error("amount mismatch on payment %s: %s", payment.pk, result.amount)
        _alert_owner(
            "مغایرت مبلغ پرداخت",
            f"سفارش {order.number}: درگاه مبلغ {result.amount} ریال را تأیید کرد، "
            f"ولی مبلغ سفارش {payment.amount} ریال است. پرداخت رد شد.",
        )
    elif payment.status == Payment.Status.PAID and not first_payment:
        _alert_owner(
            "پرداخت تکراری",
            f"سفارش {order.number} دو بار پرداخت شده است (کد پیگیری {payment.ref_id}). "
            "مبلغ اضافه باید برگردانده شود.",
        )
    if payment.status == Payment.Status.PAID:
        _fulfil_safely(order)
    return payment


def _fulfil_safely(order):
    # The money is recorded; a delivery error must not show the customer a crash.
    # `reconcile` retries orders that stay unfulfilled.
    try:
        orders.fulfil(order)
    except Exception:
        logger.exception("fulfilment failed for order %s", order.number)


def reconcile() -> int:
    """Every 10 minutes: finish open payments and undelivered paid orders."""
    now = timezone.now()
    open_payments = Payment.objects.filter(
        status=Payment.Status.INITIATED,
        created_at__lte=now - RECONCILE_AFTER,
        created_at__gte=now - RECONCILE_UNTIL,
    ).exclude(authority="")
    checked = 0
    for payment in open_payments:
        settle(payment.pk)
        checked += 1
    orders.retry_unfulfilled()
    return checked


def _alert_owner(subject: str, message: str):
    site_settings = SiteSettings.for_default_site()
    if site_settings and site_settings.notify_email:
        send_email(
            site_settings.notify_email,
            subject,
            "notifications/email/owner_alert.txt",
            {"message": message},
        )
    else:
        logger.error("owner alert not delivered: %s: %s", subject, message)
