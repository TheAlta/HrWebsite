"""Order lifecycle (spec section 7, section 8.2)."""

import logging
import uuid
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from .models import Order, OrderItem
from .signals import order_paid

logger = logging.getLogger(__name__)

NUMBER_OFFSET = 100_000


@dataclass
class OrderLine:
    item: object  # any model instance
    title: str
    unit_price: int  # Rials
    qty: int = 1


@transaction.atomic
def create_order(user, lines: list[OrderLine]) -> Order:
    subtotal = sum(line.unit_price * line.qty for line in lines)
    # Temporary unique value: the real number needs the primary key
    order = Order.objects.create(
        user=user, number=uuid.uuid4().hex[:20], subtotal=subtotal, total=subtotal
    )
    order.number = str(NUMBER_OFFSET + order.pk)
    order.save(update_fields=["number"])
    OrderItem.objects.bulk_create(
        OrderItem(
            order=order,
            item=line.item,
            title_snapshot=line.title[:300],
            unit_price=line.unit_price,
            qty=line.qty,
        )
        for line in lines
    )
    return order


def mark_paid(order: Order) -> bool:
    """Record that money arrived. Returns False if the order was already paid.

    A cancelled order can become paid: a late verified payment is a fact, and
    the receiver decides what to do with it. Call inside a transaction.
    """
    if order.status == Order.Status.PAID:
        return False
    order.status = Order.Status.PAID
    order.paid_at = timezone.now()
    order.save(update_fields=["status", "paid_at", "updated_at"])
    return True


def fulfil(order: Order) -> bool:
    """Send `order_paid` exactly once per order.

    The row lock makes concurrent calls wait; `fulfilled_at` is set in the same
    transaction as the receivers' work, so a crash leaves it empty for a retry.
    """
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.status != Order.Status.PAID or locked.fulfilled_at:
            return False
        order_paid.send(sender=Order, order=locked)
        locked.fulfilled_at = timezone.now()
        locked.save(update_fields=["fulfilled_at", "updated_at"])
    return True


def cancel_unpaid(order: Order) -> bool:
    updated = Order.objects.filter(pk=order.pk, status=Order.Status.PENDING).update(
        status=Order.Status.CANCELLED, updated_at=timezone.now()
    )
    return bool(updated)


def retry_unfulfilled() -> int:
    """Paid orders whose delivery did not finish (worker crash, transient error)."""
    done = 0
    for order in Order.objects.filter(status=Order.Status.PAID, fulfilled_at__isnull=True):
        try:
            done += fulfil(order)
        except Exception:
            logger.exception("fulfilment failed for order %s", order.number)
    return done
