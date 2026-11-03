from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import Invoice
from apps.content.models import HomePage
from apps.events.models import EventIndexPage, EventPage, Registration
from apps.orders import services as orders
from apps.orders.services import OrderLine
from apps.shop.models import DownloadToken, Product

pytestmark = pytest.mark.django_db

PAGES = ["account", "orders", "invoices", "sessions", "courses", "downloads", "profile"]


@pytest.fixture
def customer(db):
    return get_user_model().objects.create_user("09121234567")


@pytest.fixture
def stranger(db):
    return get_user_model().objects.create_user("09351112233")


def order_for(user, title="خدمت نمونه", total=10_000_000):
    return orders.create_order(user, [OrderLine(user, title, total)])


def pay(order):
    with transaction.atomic():
        orders.mark_paid(order)
    orders.fulfil(order)


@pytest.mark.parametrize("name", PAGES)
def test_every_page_needs_login(client, name):
    response = client.get(reverse(f"accounts:{name}"))
    assert response.status_code == 302 and "/login" in response.url


@pytest.mark.parametrize("name", PAGES)
def test_every_page_opens_and_marks_its_menu_item(client, customer, name):
    client.force_login(customer)
    response = client.get(reverse(f"accounts:{name}"))
    assert response.status_code == 200
    assert 'aria-current="page"' in response.content.decode()
    assert response.context["section"] == ("home" if name == "account" else name)


def test_overview_lists_unpaid_orders_only(client, customer):
    unpaid = order_for(customer, "پرداخت‌نشده")
    pay(order_for(customer, "پرداخت‌شده"))
    client.force_login(customer)
    content = client.get(reverse("accounts:account")).content.decode()
    assert "پرداخت‌نشده" in content
    assert reverse("orders:detail", args=[unpaid.number]) in content
    assert "پرداخت‌شده" not in content


def test_orders_and_invoices_show_only_the_customers_own(client, customer, stranger):
    pay(order_for(customer, "سفارش من"))
    pay(order_for(stranger, "سفارش دیگری"))
    client.force_login(customer)
    content = client.get(reverse("accounts:orders")).content.decode()
    assert "سفارش من" in content and "سفارش دیگری" not in content
    invoices = client.get(reverse("accounts:invoices"))
    mine = Invoice.objects.get(order__user=customer)
    theirs = Invoice.objects.get(order__user=stranger)
    content = invoices.content.decode()
    assert reverse("billing:invoice", args=[mine.number]) in content
    assert reverse("billing:invoice", args=[theirs.number]) not in content


def test_long_lists_are_paged(client, customer):
    for i in range(12):
        order_for(customer, f"سفارش {i}")
    client.force_login(customer)
    first = client.get(reverse("accounts:orders"))
    assert len(first.context["page_obj"]) == 10
    second = client.get(reverse("accounts:orders"), {"page": 2})
    assert len(second.context["page_obj"]) == 2
    assert client.get(reverse("accounts:orders"), {"page": "x"}).status_code == 200
    assert client.get(reverse("accounts:orders"), {"page": 99}).status_code == 200


def test_courses_and_next_course(client, customer):
    index = EventIndexPage(title="رویدادها", slug="events")
    HomePage.objects.get().add_child(instance=index)
    start = timezone.now() + timedelta(days=3)
    event = EventPage(
        title="دوره من", slug="mine", start_at=start, end_at=start + timedelta(hours=1)
    )
    index.add_child(instance=event)
    Registration.objects.create(event=event, user=customer, status=Registration.Status.PAID)
    client.force_login(customer)
    assert "دوره من" in client.get(reverse("accounts:courses")).content.decode()
    assert client.get(reverse("accounts:account")).context["next_course"].event == event


def test_downloads_show_own_files(client, customer, stranger):
    product = Product.objects.create(
        title="فایل من", slug="f", kind=Product.Kind.DIGITAL, file="products/x.pdf"
    )
    order = order_for(customer)
    DownloadToken.objects.create(
        user=customer,
        product=product,
        order=order,
        expires_at=timezone.now() + timedelta(days=1),
        downloads_left=5,
    )
    client.force_login(stranger)
    assert "فایل من" not in client.get(reverse("accounts:downloads")).content.decode()
    client.force_login(customer)
    assert "فایل من" in client.get(reverse("accounts:downloads")).content.decode()


def test_profile_saves_name_for_invoices(client, customer):
    client.force_login(customer)
    response = client.post(
        reverse("accounts:profile"),
        {"first_name": "علي", "last_name": "رضایی", "email": "ali@example.com"},
    )
    assert response.url == reverse("accounts:profile")
    customer.refresh_from_db()
    assert customer.first_name == "علی"  # Arabic yeh normalised
    assert customer.email == "ali@example.com"
    pay(order_for(customer))
    assert Invoice.objects.get().buyer_snapshot["name"] == "علی رضایی"


def test_profile_rejects_a_bad_email_and_cannot_change_the_mobile(client, customer):
    client.force_login(customer)
    response = client.post(
        reverse("accounts:profile"),
        {"first_name": "علی", "last_name": "", "email": "not-an-email", "mobile": "09350000000"},
    )
    assert response.status_code == 200
    customer.refresh_from_db()
    assert customer.mobile == "09121234567"
    assert customer.email == ""


def test_overview_asks_for_a_name_until_it_is_set(client, customer):
    client.force_login(customer)
    assert "مشخصات من" in client.get(reverse("accounts:account")).content.decode()
    customer.first_name = "علی"
    customer.save()
    assert "سلام علی" in client.get(reverse("accounts:account")).content.decode()
