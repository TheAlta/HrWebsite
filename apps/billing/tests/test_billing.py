import datetime as dt
import threading
from datetime import timedelta
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.db import connection, transaction
from django.urls import reverse
from django.utils import timezone
from wagtail.test.utils.form_data import inline_formset, nested_form_data

from apps.accounts.models import Organization
from apps.billing import services
from apps.billing.models import Invoice, ProForma, ProFormaLine
from apps.booking import services as booking_services
from apps.booking.models import Availability, Booking, SessionType
from apps.content.models import HomePage, SiteSettings
from apps.events import services as event_services
from apps.events.models import EventIndexPage, EventPage, Registration
from apps.notifications.testing import CapturingSMS
from apps.orders import services as orders
from apps.orders.models import Order, Refund
from apps.orders.services import OrderError, OrderLine
from apps.payments import services as payments
from apps.payments.models import MANUAL_GATEWAY, Payment
from apps.shop import services as shop
from apps.shop.cart import Cart
from apps.shop.models import Coupon, DownloadToken, Product, Shipment

pytestmark = pytest.mark.django_db

ADDRESS = {
    "recipient": "علی رضایی",
    "mobile": "09121234567",
    "province": "تهران",
    "city": "تهران",
    "address": "خیابان نمونه",
    "postal_code": "1234567890",
}


@pytest.fixture
def customer(db):
    return get_user_model().objects.create_user(
        "09121234567", first_name="علی", last_name="رضایی", email="ali@example.com"
    )


@pytest.fixture
def other_customer(db):
    return get_user_model().objects.create_user("09351112233")


@pytest.fixture
def admin_client(client, django_user_model):
    client.force_login(django_user_model.objects.create_superuser("09120000000", password="x"))
    return client


def make_order(user, total=10_000_000, **kwargs):
    return orders.create_order(user, [OrderLine(user, "خدمت نمونه", total)], **kwargs)


def pay(order):
    with transaction.atomic():
        orders.mark_paid(order)
    orders.fulfil(order)
    order.refresh_from_db()


def sms_templates(user):
    return [m["template"] for m in CapturingSMS.outbox if m["to"] == user.mobile]


# --- invoices ---------------------------------------------------------------------------


def test_paid_order_gets_an_invoice_once(customer):
    order = make_order(customer)
    pay(order)
    orders.fulfil(order)
    invoice = Invoice.objects.get()
    assert invoice.order == order
    assert invoice.number == 1


def test_numbers_run_without_gaps(customer):
    for _ in range(3):
        pay(make_order(customer))
    assert sorted(Invoice.objects.values_list("number", flat=True)) == [1, 2, 3]


def test_a_failed_delivery_does_not_burn_a_number(customer):
    first, second = make_order(customer), make_order(customer)
    with (
        mock.patch("apps.billing.services._notify", side_effect=RuntimeError),
        pytest.raises(RuntimeError),
        transaction.atomic(),
    ):
        services.issue_invoice(first)
    pay(second)
    assert Invoice.objects.get().number == 1


def test_free_order_has_no_invoice(customer):
    pay(make_order(customer, total=0))
    assert not Invoice.objects.exists()


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_parallel_payments_get_different_numbers(customer):
    """Real parallel transactions: numbers stay unique and gapless."""
    first, second = make_order(customer), make_order(customer)
    barrier = threading.Barrier(2)

    def attempt(order):
        barrier.wait()
        try:
            pay(order)
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt, args=[o]) for o in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(Invoice.objects.values_list("number", flat=True)) == [1, 2]


def test_later_changes_never_alter_an_issued_invoice(customer):
    pay(make_order(customer))
    invoice = Invoice.objects.get()
    customer.first_name = "نام جدید"
    customer.save()
    site_settings = SiteSettings.for_default_site()
    site_settings.seller_name = "فروشنده جدید"
    site_settings.save()
    invoice.refresh_from_db()
    assert invoice.buyer_snapshot["name"] == "علی رضایی"
    assert invoice.seller_snapshot["name"] != "فروشنده جدید"


def test_seller_comes_from_the_panel(customer):
    site_settings = SiteSettings.for_default_site()
    site_settings.seller_name = "آرزو نمونه"
    site_settings.seller_economic_code = "411111111111"
    site_settings.save()
    pay(make_order(customer))
    assert Invoice.objects.get().seller_snapshot["economic_code"] == "411111111111"


def test_customer_is_told_by_sms_and_email(customer):
    pay(make_order(customer))
    assert "order-invoice" in sms_templates(customer)
    assert "/account/invoices/1/" in mail.outbox[-1].body


def test_no_email_without_an_address(other_customer):
    pay(make_order(other_customer))
    assert "order-invoice" in sms_templates(other_customer)
    assert not mail.outbox


# --- invoice file -----------------------------------------------------------------------


def invoice_url(number=1):
    return reverse("billing:invoice", args=[number])


def body(response):
    return b"".join(response.streaming_content)


def test_buyer_downloads_a_real_pdf(client, customer):
    pay(make_order(customer))
    client.force_login(customer)
    response = client.get(invoice_url())
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Cache-Control"] == "private, no-store"
    assert body(response).startswith(b"%PDF")


def test_file_is_rendered_once(client, customer):
    pay(make_order(customer))
    client.force_login(customer)
    with mock.patch("apps.billing.services.render_pdf", return_value=b"%PDF-1") as render:
        body(client.get(invoice_url()))
        body(client.get(invoice_url()))
    assert render.call_count == 1


def test_another_customer_gets_404(client, customer, other_customer):
    pay(make_order(customer))
    client.force_login(other_customer)
    assert client.get(invoice_url()).status_code == 404


def test_invoice_needs_login(client, customer):
    pay(make_order(customer))
    response = client.get(invoice_url())
    assert response.status_code == 302 and "/login" in response.url


def test_staff_with_permission_can_open_it(client, customer, django_user_model):
    pay(make_order(customer))
    staff = django_user_model.objects.create_user("09120000001")
    staff.user_permissions.add(Permission.objects.get(codename="view_invoice"))
    client.force_login(staff)
    assert client.get(invoice_url()).status_code == 200


def test_invoice_file_is_outside_media(client, settings, customer):
    pay(make_order(customer))
    client.force_login(customer)
    body(client.get(invoice_url()))
    invoice = Invoice.objects.get()
    assert str(settings.MEDIA_ROOT) not in invoice.pdf_file.path
    assert client.get(f"/media/{invoice.pdf_file.name}").status_code == 404


# --- refund -----------------------------------------------------------------------------


def test_refund_marks_order_and_voids_invoice(customer, django_user_model):
    order = make_order(customer)
    pay(order)
    staff = django_user_model.objects.create_user("09120000001")
    refund = orders.refund(order, by=staff, reference="R1", note="درخواست مشتری")
    order.refresh_from_db()
    invoice = Invoice.objects.get()
    assert order.status == Order.Status.REFUNDED
    assert (refund.amount, refund.reference, refund.created_by) == (order.total, "R1", staff)
    assert invoice.is_void and invoice.number == 1
    assert "order-refunded" in sms_templates(customer)


def test_voided_invoice_renders_again_with_its_stamp(client, customer):
    order = make_order(customer)
    pay(order)
    client.force_login(customer)
    body(client.get(invoice_url()))
    orders.refund(order)
    with mock.patch("apps.billing.services.render_pdf", return_value=b"%PDF-1") as render:
        body(client.get(invoice_url()))
    assert render.call_args.args[1]["is_void"] is True


def test_numbers_are_not_reused_after_a_refund(customer):
    order = make_order(customer)
    pay(order)
    orders.refund(order)
    pay(make_order(customer))
    assert sorted(Invoice.objects.values_list("number", flat=True)) == [1, 2]


@pytest.mark.parametrize("status", ["pending", "cancelled", "refunded"])
def test_only_a_paid_order_can_be_refunded(customer, status):
    order = make_order(customer)
    Order.objects.filter(pk=order.pk).update(status=status)
    with pytest.raises(OrderError):
        orders.refund(order)
    assert not Refund.objects.exists()


def test_late_payment_on_a_refunded_order_stays_refunded(customer):
    order = make_order(customer)
    pay(order)
    orders.refund(order)
    order.refresh_from_db()
    with transaction.atomic():
        assert orders.mark_paid(order) is False
    order.refresh_from_db()
    assert order.status == Order.Status.REFUNDED


def book_session(user):
    session = SessionType.objects.create(
        title="جلسه", mode="online", duration_min=60, price=25_000_000, buffer_min=0
    )
    for weekday in Availability.Weekday.values:
        Availability.objects.create(
            weekday=weekday, start_time=dt.time(9, 0), end_time=dt.time(17, 0)
        )
    slot = booking_services.free_slots(session)[3].slots[0]
    return session, booking_services.hold_slot(user, session, slot)


def test_refund_frees_the_session_without_a_refund_reminder(customer):
    site_settings = SiteSettings.for_default_site()
    site_settings.notify_email = "owner@example.com"
    site_settings.save()
    session, booking = book_session(customer)
    pay(booking.order)
    start = booking.start_at
    orders.refund(booking.order)
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED
    assert booking_services.is_free(session, start)
    assert not [m for m in mail.outbox if "لغو جلسه" in m.subject]


def test_cancelling_an_unpaid_order_frees_the_session(customer):
    session, booking = book_session(customer)
    start = booking.start_at
    orders.cancel_by_owner(booking.order)
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED
    assert booking.order.status == Order.Status.CANCELLED
    assert booking_services.is_free(session, start)


@pytest.fixture
def event(db):
    index = EventIndexPage(title="رویدادها", slug="events")
    HomePage.objects.get().add_child(instance=index)
    start = timezone.now() + timedelta(days=5)
    page = EventPage(
        title="دوره",
        slug="course",
        start_at=start,
        end_at=start + timedelta(hours=2),
        price=10_000_000,
        capacity=1,
    )
    index.add_child(instance=page)
    return page


def test_refund_gives_the_seat_to_the_waiting_list(event, customer, other_customer):
    registration = event_services.register(customer, event)
    pay(registration.order)
    waiting = event_services.register(other_customer, event)
    assert waiting.status == Registration.Status.WAITLIST
    orders.refund(registration.order)
    registration.refresh_from_db()
    waiting.refresh_from_db()
    assert registration.status == Registration.Status.CANCELLED
    assert waiting.status == Registration.Status.PENDING


def test_cancelling_an_unpaid_order_frees_the_seat(event, customer):
    registration = event_services.register(customer, event)
    orders.cancel_by_owner(registration.order)
    registration.refresh_from_db()
    assert registration.status == Registration.Status.CANCELLED
    assert event_services.seats_left(event) == 1


def make_cart(*products, code=""):
    from django.contrib.sessions.backends.db import SessionStore

    cart = Cart(SessionStore())
    for product in products:
        cart.add(product)
    cart.coupon_code = code
    return cart


@pytest.fixture
def book(db):
    return Product.objects.create(title="کتاب", slug="book", price=3_000_000, stock=2)


@pytest.fixture
def ebook(db):
    return Product.objects.create(
        title="فایل", slug="file", kind=Product.Kind.DIGITAL, price=500_000, file="products/x.pdf"
    )


def stock(product):
    return Product.objects.get(pk=product.pk).stock


def test_refund_takes_back_stock_and_download_links(book, ebook, customer):
    order = shop.place_order(customer, make_cart(book, ebook), ADDRESS)
    pay(order)
    assert stock(book) == 1
    orders.refund(order)
    assert stock(book) == 2
    assert Shipment.objects.get().status == Shipment.Status.CANCELLED
    assert not DownloadToken.objects.get().is_valid


def test_book_already_shipped_is_not_restocked(book, customer):
    order = shop.place_order(customer, make_cart(book), ADDRESS)
    pay(order)
    Shipment.objects.update(status=Shipment.Status.SHIPPED)
    orders.refund(order)
    assert stock(book) == 1
    assert Shipment.objects.get().status == Shipment.Status.SHIPPED


def test_stock_returns_once_when_a_released_order_is_cancelled(book, customer):
    order = shop.place_order(customer, make_cart(book), ADDRESS)
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(hours=1))
    shop.release_unpaid()
    assert stock(book) == 2
    Order.objects.filter(pk=order.pk).update(status=Order.Status.PAID)
    orders.refund(order)
    assert stock(book) == 2


def test_refund_gives_the_coupon_use_back(book, customer, other_customer):
    Coupon.objects.create(code="ONE", value=10, max_uses=1)
    order = shop.place_order(customer, make_cart(book, code="ONE"), ADDRESS)
    pay(order)
    orders.refund(order)
    assert shop.place_order(other_customer, make_cart(book, code="ONE"), ADDRESS).discount


def test_cancel_refuses_a_paid_order(customer):
    order = make_order(customer)
    pay(order)
    with pytest.raises(OrderError):
        orders.cancel_by_owner(order)


def test_late_payment_after_a_panel_cancel_takes_stock_again(book, customer):
    order = shop.place_order(customer, make_cart(book), ADDRESS)
    orders.cancel_by_owner(order)
    assert stock(book) == 2
    order.refresh_from_db()
    pay(order)
    assert stock(book) == 1
    assert Shipment.objects.get().status == Shipment.Status.PREPARING


# --- manual payment ---------------------------------------------------------------------


def test_manual_payment_delivers_and_issues_an_invoice(customer):
    order = make_order(customer)
    payment = payments.record_manual_payment(order, method="cheque", reference="123")
    order.refresh_from_db()
    assert order.status == Order.Status.PAID
    assert (payment.gateway, payment.ref_id, payment.amount) == (MANUAL_GATEWAY, "123", order.total)
    assert order.fulfilled_at is not None
    assert Invoice.objects.filter(order=order).exists()


def test_manual_payment_twice_is_refused(customer):
    order = make_order(customer)
    payments.record_manual_payment(order, method="transfer", reference="1")
    with pytest.raises(OrderError):
        payments.record_manual_payment(order, method="transfer", reference="1")
    assert Payment.objects.count() == 1


def test_reconcile_leaves_manual_payments_alone(customer):
    order = make_order(customer)
    payments.record_manual_payment(order, method="transfer", reference="1")
    Payment.objects.update(created_at=timezone.now() - timedelta(hours=1))
    assert payments.reconcile() == 0


# --- pre-invoice ------------------------------------------------------------------------


@pytest.fixture
def organization(db):
    return Organization.objects.create(
        name="شرکت نمونه", national_id="10101010101", economic_code="4111", address="اصفهان"
    )


def make_proforma(organization=None, mobile="09121234567", price=50_000_000):
    proforma = ProForma.objects.create(
        organization=organization, mobile=mobile, contact_name="رابط نمونه"
    )
    ProFormaLine.objects.create(proforma=proforma, title="آموزش سازمانی", qty=2, unit_price=price)
    return proforma


def test_sending_creates_the_order_and_texts_the_link(organization):
    proforma = services.send_proforma(make_proforma(organization))
    order = proforma.order
    assert proforma.status == ProForma.Status.SENT
    assert (order.total, order.organization) == (100_000_000, organization)
    assert order.items.get().qty == 2
    assert order.user.mobile == "09121234567"
    message = CapturingSMS.outbox[-1]
    assert message["template"] == "proforma-ready"
    assert message["params"]["token2"] == order.number


def test_sending_uses_an_existing_customer(customer, organization):
    proforma = services.send_proforma(make_proforma(organization))
    assert proforma.order.user == customer


def test_sending_twice_is_refused(organization):
    proforma = services.send_proforma(make_proforma(organization))
    with pytest.raises(OrderError):
        services.send_proforma(proforma)
    assert Order.objects.count() == 1


def test_empty_proforma_is_refused():
    proforma = ProForma.objects.create(mobile="09121234567")
    with pytest.raises(OrderError):
        services.send_proforma(proforma)


def test_paying_online_closes_the_proforma_and_names_the_company(organization):
    proforma = services.send_proforma(make_proforma(organization))
    pay(proforma.order)
    proforma.refresh_from_db()
    assert proforma.status == ProForma.Status.PAID
    buyer = Invoice.objects.get().buyer_snapshot
    assert (buyer["organization"], buyer["national_id"]) == ("شرکت نمونه", "10101010101")


def test_cheque_closes_the_proforma(organization):
    proforma = services.send_proforma(make_proforma(organization))
    payments.record_manual_payment(proforma.order, method="cheque", reference="9")
    proforma.refresh_from_db()
    assert proforma.status == ProForma.Status.PAID


def test_cancelling_a_sent_proforma_cancels_its_order(organization):
    proforma = services.cancel_proforma(services.send_proforma(make_proforma(organization)))
    assert proforma.status == ProForma.Status.CANCELLED
    assert proforma.order.status == Order.Status.CANCELLED


def test_cancelling_a_draft_needs_no_order(organization):
    assert services.cancel_proforma(make_proforma(organization)).order is None


def test_refund_cancels_the_proforma(organization):
    proforma = services.send_proforma(make_proforma(organization))
    pay(proforma.order)
    orders.refund(proforma.order)
    proforma.refresh_from_db()
    assert proforma.status == ProForma.Status.CANCELLED


def test_customer_opens_the_proforma_pdf(client, customer, other_customer, organization):
    proforma = services.send_proforma(make_proforma(organization))
    url = reverse("billing:proforma", args=[proforma.pk])
    client.force_login(other_customer)
    assert client.get(url).status_code == 404
    client.force_login(customer)
    response = client.get(url)
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def test_order_page_links_the_documents(client, customer, organization):
    proforma = services.send_proforma(make_proforma(organization))
    pay(proforma.order)
    client.force_login(customer)
    content = client.get(reverse("orders:detail", args=[proforma.order.number])).content.decode()
    assert invoice_url() in content
    assert reverse("billing:proforma", args=[proforma.pk]) in content


# --- panel ------------------------------------------------------------------------------


def test_refund_from_the_panel(admin_client, customer):
    order = make_order(customer)
    pay(order)
    page = admin_client.get(reverse("panel_orders:inspect", args=[order.pk])).content.decode()
    url = reverse("panel_orders:refund", args=[order.pk])
    assert url in page
    assert admin_client.get(url).status_code == 200
    assert admin_client.post(url, {"reference": "R9", "note": ""}).status_code == 302
    assert Refund.objects.get().reference == "R9"


def test_refunding_twice_in_the_panel_shows_an_error(admin_client, customer):
    order = make_order(customer)
    pay(order)
    url = reverse("panel_orders:refund", args=[order.pk])
    admin_client.post(url, {"reference": "R9"})
    response = admin_client.post(url, {"reference": "R9"}, follow=True)
    assert response.status_code == 200
    assert Refund.objects.count() == 1


def test_panel_buttons_follow_the_order_status(admin_client, customer):
    order = make_order(customer)
    inspect = reverse("panel_orders:inspect", args=[order.pk])
    page = admin_client.get(inspect).content.decode()
    assert reverse("panel_orders:manual_payment", args=[order.pk]) in page
    assert reverse("panel_orders:cancel", args=[order.pk]) in page
    assert reverse("panel_orders:refund", args=[order.pk]) not in page


def test_manual_payment_and_cancel_from_the_panel(admin_client, customer):
    paid, cancelled = make_order(customer), make_order(customer)
    url = reverse("panel_orders:manual_payment", args=[paid.pk])
    assert admin_client.get(url).status_code == 200
    data = {"method": "transfer", "reference": "55"}
    assert admin_client.post(url, data).status_code == 302
    paid.refresh_from_db()
    assert paid.status == Order.Status.PAID

    url = reverse("panel_orders:cancel", args=[cancelled.pk])
    assert admin_client.post(url).status_code == 302
    cancelled.refresh_from_db()
    assert cancelled.status == Order.Status.CANCELLED


def test_refund_needs_the_refund_permission(client, customer, django_user_model):
    order = make_order(customer)
    pay(order)
    support = django_user_model.objects.create_user("09120000001", is_staff=True)
    group = Group.objects.create(name="آزمایشی")
    group.permissions.add(
        Permission.objects.get(codename="access_admin"),
        Permission.objects.get(codename="view_order"),
    )
    support.groups.add(group)
    client.force_login(support)
    url = reverse("panel_orders:refund", args=[order.pk])
    response = client.post(url, {"reference": "X"})
    assert response.status_code in (302, 403)
    assert not Refund.objects.exists()
    page = client.get(reverse("panel_orders:inspect", args=[order.pk])).content.decode()
    assert url not in page


def test_proforma_from_the_panel(admin_client, organization):
    data = nested_form_data(
        {
            "organization": organization.pk,
            "contact_name": "رابط",
            "mobile": "۰۹۱۲۱۲۳۴۵۶۷",
            "valid_until": "۱۴۰۵/۰۹/۰۱ ۱۲:۰۰",
            "note": "",
            "lines": inline_formset(
                [{"title": "کارگاه", "qty": "1", "unit_price": "70000000", "ORDER": "1"}]
            ),
        }
    )
    assert admin_client.post(reverse("panel_proformas:add"), data).status_code == 302
    proforma = ProForma.objects.get()
    assert proforma.total == 70_000_000

    inspect = reverse("panel_proformas:inspect", args=[proforma.pk])
    assert reverse("panel_proformas:send", args=[proforma.pk]) in (
        admin_client.get(inspect).content.decode()
    )
    assert admin_client.post(reverse("panel_proformas:send", args=[proforma.pk])).status_code == 302
    proforma.refresh_from_db()
    assert proforma.status == ProForma.Status.SENT

    edit = reverse("panel_proformas:edit", args=[proforma.pk])
    assert admin_client.post(edit, data).status_code == 200  # refused, shown again with the error


def test_panel_lists_open(admin_client, customer, organization):
    pay(make_order(customer))
    for name in (
        "panel_invoices:index",
        "panel_proformas:index",
        "panel_organizations:index",
        "panel_refunds:index",
        "panel_orders:index",
    ):
        assert admin_client.get(reverse(name)).status_code == 200
    invoice = Invoice.objects.get()
    page = admin_client.get(reverse("panel_invoices:inspect", args=[invoice.pk])).content.decode()
    assert invoice_url() in page
