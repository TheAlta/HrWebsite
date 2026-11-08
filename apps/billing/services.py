"""Invoices (PAY-2, spec section 7)."""

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import connection, transaction
from django.db.models import Max
from django.urls import reverse
from django.utils import timezone

from apps.content.models import SiteSettings
from apps.core.http import absolute_url
from apps.core.pdf import render_pdf
from apps.notifications.services import send_email, send_sms
from apps.orders import services as orders
from apps.orders.models import Order
from apps.orders.services import OrderLine

from .models import Invoice, ProForma

INVOICE_LOCK_ID = 7_140_502  # any fixed number unique to this lock


def _lock_numbering():
    """One invoice at a time, until the transaction ends, so numbers have no gaps.

    A database sequence would skip a number whenever a transaction rolls back.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [INVOICE_LOCK_ID])


def seller_snapshot() -> dict:
    site_settings = SiteSettings.for_default_site()
    if site_settings is None:
        return {}
    return {
        "name": site_settings.seller_name or site_settings.brand_name,
        "national_id": site_settings.seller_national_id,
        "economic_code": site_settings.seller_economic_code,
        "address": site_settings.seller_address or site_settings.address,
        "postal_code": site_settings.seller_postal_code,
        "phone": site_settings.phone,
    }


def buyer_snapshot(order: Order) -> dict:
    user = order.user
    buyer = {"name": user.get_full_name(), "mobile": user.mobile, "email": user.email}
    if order.organization:
        organization = order.organization
        buyer |= {
            "organization": organization.name,
            "national_id": organization.national_id,
            "economic_code": organization.economic_code,
            "address": organization.address,
        }
    return buyer


def issue_invoice(order: Order) -> Invoice | None:
    """Receiver of `order_paid`, inside the delivery transaction. Free orders sell nothing."""
    if order.total == 0:
        return None
    _lock_numbering()
    last = Invoice.objects.aggregate(last=Max("number"))["last"] or 0
    invoice = Invoice.objects.create(
        order=order,
        number=last + 1,
        buyer_snapshot=buyer_snapshot(order),
        seller_snapshot=seller_snapshot(),
    )
    _notify(invoice)
    return invoice


def _notify(invoice: Invoice) -> None:
    user = invoice.order.user
    send_sms(user.mobile, "order_invoice", {"token": str(invoice.number)})
    if user.email:
        send_email(
            user.email,
            f"فاکتور شماره {invoice.number}",
            "billing/email/invoice.txt",
            {"invoice": invoice, "url": absolute_url(invoice_url(invoice))},
        )


def invoice_url(invoice: Invoice) -> str:
    return reverse("billing:invoice", args=[invoice.number])


def void_invoice(order: Order) -> None:
    """A refunded order keeps its number; the document says it is void."""
    Invoice.objects.filter(order=order, voided_at__isnull=True).update(
        voided_at=timezone.now(), pdf_file=""
    )
    ProForma.objects.filter(order=order).update(status=ProForma.Status.CANCELLED)


def send_proforma(proforma: ProForma) -> ProForma:
    """Create the order behind a pre-invoice and text its link to the contact (PAY-3)."""
    with transaction.atomic():
        proforma = ProForma.objects.select_for_update().get(pk=proforma.pk)
        if proforma.status != ProForma.Status.DRAFT:
            raise orders.OrderError("این پیش‌فاکتور قبلاً ارسال شده است.")
        lines = [
            OrderLine(line, line.title, line.unit_price, line.qty) for line in proforma.lines.all()
        ]
        if not lines or proforma.total == 0:
            raise orders.OrderError("پیش‌فاکتور باید مبلغ داشته باشد.")
        users = get_user_model().objects
        user = users.filter(mobile=proforma.mobile).first() or users.create_user(proforma.mobile)
        proforma.order = orders.create_order(user, lines, organization=proforma.organization)
        proforma.status = ProForma.Status.SENT
        proforma.save(update_fields=["order", "status"])
        send_sms(
            proforma.mobile,
            "proforma_ready",
            {"token": str(proforma.pk), "token2": proforma.order.number},
        )
    return proforma


def cancel_proforma(proforma: ProForma) -> ProForma:
    """A draft is simply closed; a sent one also cancels its unpaid order."""
    if proforma.order:
        orders.cancel_by_owner(proforma.order)  # the receiver marks it cancelled
    else:
        ProForma.objects.filter(pk=proforma.pk).update(status=ProForma.Status.CANCELLED)
    proforma.refresh_from_db()
    return proforma


def mark_proforma_paid(order: Order) -> None:
    ProForma.objects.filter(order=order).update(status=ProForma.Status.PAID)


def _document_context(order: Order, buyer: dict, seller: dict) -> dict:
    return {
        "order": order,
        "lines": order.items.all(),
        "buyer": buyer,
        "seller": seller,
    }


def invoice_pdf(invoice: Invoice):
    """The invoice file, rendered on first use. A customer waits under a second, once."""
    if invoice.pdf_file and invoice.pdf_file.storage.exists(invoice.pdf_file.name):
        return invoice.pdf_file.open("rb")
    content = render_pdf(
        "billing/document.html",
        {
            **_document_context(invoice.order, invoice.buyer_snapshot, invoice.seller_snapshot),
            "title": "فاکتور فروش",
            "number": invoice.number,
            "date": invoice.issued_at,
            "is_void": invoice.is_void,
        },
    )
    invoice.pdf_file.save(f"invoice-{invoice.number}.pdf", ContentFile(content), save=False)
    Invoice.objects.filter(pk=invoice.pk).update(pdf_file=invoice.pdf_file.name)
    return invoice.pdf_file.open("rb")


def proforma_pdf(proforma: ProForma) -> bytes:
    """Rendered each time: unlike an invoice it is an offer, not a record to keep."""
    order = proforma.order
    buyer = buyer_snapshot(order)
    buyer["name"] = proforma.contact_name or buyer["name"]
    return render_pdf(
        "billing/document.html",
        {
            **_document_context(order, buyer, seller_snapshot()),
            "title": "پیش‌فاکتور",
            "number": proforma.pk,
            "date": proforma.created_at,
            "valid_until": proforma.valid_until,
            "note": proforma.note,
        },
    )
