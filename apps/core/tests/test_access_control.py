"""OWASP A01, broken access control: every private address, tried by someone else.

One customer owns one of everything private. Another customer, and a visitor who
is not logged in, try each address. The answer must give nothing away: 404 for
the other customer (the same as an address that does not exist), the login page
for the visitor. REPORT #052.
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import Invoice
from apps.booking.models import Booking, SessionType
from apps.certificates.models import Certificate
from apps.content.models import HomePage
from apps.events.models import EventIndexPage, EventPage, Registration
from apps.orders import services as orders
from apps.orders.services import OrderLine
from apps.shop.models import DownloadToken, Product

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user("09121234567", first_name="مالک")


@pytest.fixture
def intruder(db):
    return get_user_model().objects.create_user("09351112233")


@pytest.fixture
def private_urls(owner):
    """(method, address) of everything only the owner may open or change."""
    order = orders.create_order(owner, [OrderLine(owner, "خدمت نمونه", 10_000_000)])
    paid = orders.create_order(owner, [OrderLine(owner, "خدمت دیگر", 20_000_000)])
    with transaction.atomic():
        orders.mark_paid(paid)
    orders.fulfil(paid)
    invoice = Invoice.objects.get(order=paid)

    session_type = SessionType.objects.create(title="جلسه", duration_min=60, price=0)
    start = timezone.now() + timedelta(days=5)
    booking = Booking.objects.create(
        user=owner,
        session_type=session_type,
        start_at=start,
        end_at=start + timedelta(hours=1),
        blocked_until=start + timedelta(hours=1),
        status=Booking.Status.CONFIRMED,
    )

    index = EventIndexPage(title="رویدادها", slug="events")
    HomePage.objects.get().add_child(instance=index)
    event = EventPage(
        title="دوره", slug="course", start_at=start, end_at=start + timedelta(hours=2)
    )
    index.add_child(instance=event)
    registration = Registration.objects.create(event=event, user=owner, status="paid")
    certificate = Certificate.objects.create(
        registration=registration,
        code="ABCDE-FGHJK",
        full_name="مالک",
        event_title=event.title,
        event_kind="دوره",
        event_start=start,
    )

    product = Product(title="فایل", slug="file", kind=Product.Kind.DIGITAL, price=500_000)
    product.file.save("guide.pdf", SimpleUploadedFile("guide.pdf", b"%PDF-1.4 secret"))
    token = DownloadToken.objects.create(
        user=owner,
        product=product,
        order=paid,
        expires_at=timezone.now() + timedelta(days=7),
        downloads_left=3,
    )
    return [
        ("get", reverse("orders:detail", args=[order.number])),
        ("post", reverse("payments:pay", args=[order.number])),
        ("get", reverse("billing:invoice", args=[invoice.number])),
        ("post", reverse("booking:cancel", args=[booking.pk])),
        ("get", reverse("booking:reschedule", args=[booking.pk])),
        ("post", reverse("events:cancel", args=[registration.pk])),
        ("get", reverse("events:join", args=[registration.pk])),
        ("get", reverse("certificates:download", args=[certificate.code])),
        ("get", reverse("shop:download", args=[token.token])),
    ]


def test_another_customer_gets_nothing(client, intruder, private_urls):
    client.force_login(intruder)
    for method, url in private_urls:
        response = getattr(client, method)(url)
        assert response.status_code == 404, f"{method.upper()} {url}"


def test_a_visitor_is_asked_to_log_in(client, private_urls):
    login = reverse("accounts:login")
    for method, url in private_urls:
        response = getattr(client, method)(url)
        assert response.status_code == 302, f"{method.upper()} {url}"
        assert response.url.startswith(login), f"{method.upper()} {url}"


def test_nothing_changed_after_the_attempts(client, intruder, owner, private_urls):
    client.force_login(intruder)
    for method, url in private_urls:
        getattr(client, method)(url)
    assert Booking.objects.get(user=owner).status == Booking.Status.CONFIRMED
    assert Registration.objects.get(user=owner).status == Registration.Status.PAID
    assert DownloadToken.objects.get(user=owner).downloads_left == 3


def test_the_owner_can_open_them(client, owner, private_urls):
    """The same addresses work for their owner, so the 404s above are not just broken links."""
    client.force_login(owner)
    for method, url in private_urls:
        if method == "get":
            assert client.get(url).status_code in (200, 302), url


def test_the_panel_is_closed_to_customers(client, intruder):
    client.force_login(intruder)
    for url in ("/panel/", "/panel/orders/", "/panel/leads/", "/panel/reports/sales/"):
        response = client.get(url)
        assert response.status_code == 302, url
        assert "/panel/login/" in response.url, url
