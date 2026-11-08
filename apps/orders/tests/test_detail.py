import pytest
from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse

from apps.orders import services as orders
from apps.orders.services import OrderLine

pytestmark = pytest.mark.django_db


@pytest.fixture
def customer(db):
    return get_user_model().objects.create_user("09121234567")


def page(client, order):
    client.force_login(order.user)
    return client.get(reverse("orders:detail", args=[order.number])).content.decode()


def test_a_paid_order_reports_a_purchase(client, customer):
    """For the analytics tool chosen at launch (docs/LAUNCH.md, item 14)."""
    order = orders.create_order(customer, [OrderLine(customer, "خدمت نمونه", 10_000_000)])
    with transaction.atomic():
        orders.mark_paid(order)
    html = page(client, order)
    assert 'data-conversion="purchase"' in html
    assert f'data-conversion-id="{order.number}"' in html
    assert 'data-conversion-value="10000000"' in html


def test_an_unpaid_order_reports_nothing(client, customer):
    order = orders.create_order(customer, [OrderLine(customer, "خدمت نمونه", 10_000_000)])
    assert "data-conversion" not in page(client, order)
