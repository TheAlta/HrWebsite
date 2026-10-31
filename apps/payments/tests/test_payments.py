import os
import subprocess
import sys
from datetime import timedelta

import httpx
import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.utils import timezone

from apps.content.models import SiteSettings
from apps.orders import services as orders
from apps.orders.models import Order
from apps.orders.services import OrderLine
from apps.orders.signals import order_paid
from apps.payments import services
from apps.payments.gateways import GatewayError
from apps.payments.gateways.zarinpal import ZarinpalGateway
from apps.payments.gateways.zibal import ZibalGateway
from apps.payments.models import Payment
from apps.payments.testing import StubGateway

pytestmark = pytest.mark.django_db

AMOUNT = 25_000_000


@pytest.fixture(autouse=True)
def stub_gateway(settings):
    settings.PAYMENT_GATEWAYS = {
        **settings.PAYMENT_GATEWAYS,
        "stub": "apps.payments.testing.StubGateway",
        "backup": "apps.payments.testing.BackupGateway",
    }
    settings.PAYMENT_GATEWAY_ORDER = ["stub"]
    StubGateway.reset()
    yield StubGateway
    StubGateway.reset()


@pytest.fixture
def customer():
    return get_user_model().objects.create_user("09121234567")


@pytest.fixture
def order(customer):
    # Any model instance can be sold; the order only keeps a generic reference
    return orders.create_order(
        customer, [OrderLine(item=customer, title="جلسه", unit_price=AMOUNT)]
    )


def start(order):
    url = services.start_payment(order, lambda name: f"https://site.test/payments/callback/{name}/")
    return url, Payment.objects.filter(order=order).latest("created_at")


def callback(client, payment, **params):
    query = {"authority": payment.authority, **params}
    return client.get(f"/payments/callback/{payment.gateway}/", query)


def test_order_number_and_totals(order):
    assert order.number == str(100_000 + order.pk)
    assert (order.subtotal, order.total, order.status) == (AMOUNT, AMOUNT, "pending")
    assert order.items.get().title_snapshot == "جلسه"


def test_successful_payment_is_verified_and_marks_order_paid(client, order):
    _, payment = start(order)
    response = callback(client, payment, Status="OK")
    assert response.status_code == 302 and response.url == f"/orders/{order.number}/"
    payment.refresh_from_db()
    order.refresh_from_db()
    assert StubGateway.verify_calls == [payment.authority]
    assert (payment.status, payment.ref_id, payment.card_mask) == ("paid", "REF1", "6037****1234")
    assert order.status == "paid" and order.paid_at and order.fulfilled_at


def test_callback_parameters_are_not_trusted(client, order):
    """A hand-made «Status=OK» URL must not pay an order (spec section 8.2)."""
    StubGateway.verify_ok = False
    _, payment = start(order)
    callback(client, payment, Status="OK")
    payment.refresh_from_db()
    order.refresh_from_db()
    assert payment.status == "failed"
    assert order.status == "pending"


def test_amount_mismatch_is_rejected_and_owner_alerted(client, order, demo_site):
    site_settings = SiteSettings.objects.get()
    site_settings.notify_email = "owner@example.com"
    site_settings.save()
    StubGateway.verify_amount = AMOUNT - 10
    _, payment = start(order)
    callback(client, payment)
    payment.refresh_from_db()
    order.refresh_from_db()
    assert payment.status == "failed" and order.status == "pending"
    assert "مغایرت مبلغ" in mail.outbox[-1].subject


def test_repeated_callback_changes_nothing(client, order):
    received = []

    def receiver(sender, order, **kwargs):
        received.append(order.pk)

    order_paid.connect(receiver)
    try:
        _, payment = start(order)
        callback(client, payment)
        callback(client, payment)
        client.post(f"/payments/callback/{payment.gateway}/", {"authority": payment.authority})
    finally:
        order_paid.disconnect(receiver)
    assert len(StubGateway.verify_calls) == 1
    assert received == [order.pk]


def test_unknown_authority_and_gateway_are_404(client, order):
    assert client.get("/payments/callback/stub/", {"authority": "nope"}).status_code == 404
    assert client.get("/payments/callback/stub/").status_code == 404
    assert client.get("/payments/callback/nope/", {"authority": "x"}).status_code == 404


def test_gateway_outage_during_verify_keeps_payment_open(client, order):
    StubGateway.verify_error = True
    _, payment = start(order)
    assert callback(client, payment).status_code == 302
    payment.refresh_from_db()
    assert payment.status == "initiated"

    # Customer closed the page; the 10-minute job finishes it later
    StubGateway.verify_error = False
    assert services.reconcile() == 0  # still too young: may be on the bank page
    Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(minutes=25))
    assert services.reconcile() == 1
    order.refresh_from_db()
    assert order.status == "paid"


def test_backup_gateway_is_used_when_primary_fails(settings, order):
    settings.PAYMENT_GATEWAY_ORDER = ["stub", "backup"]
    StubGateway.fail_request = True
    url, payment = start(order)
    assert url.startswith("https://backup.test/") and payment.gateway == "backup"
    failed = Payment.objects.get(order=order, gateway="stub")
    assert failed.status == "failed"


def test_no_gateway_available(client, customer, order):
    StubGateway.fail_request = True
    client.force_login(customer)
    response = client.post(f"/payments/pay/{order.number}/")
    assert response.status_code == 302 and response.url == f"/orders/{order.number}/"


def test_retry_button_starts_a_new_payment(client, customer, order):
    client.force_login(customer)
    response = client.post(f"/payments/pay/{order.number}/")
    assert response.url.startswith("https://bank.test/")
    assert "پرداخت" in client.get(f"/orders/{order.number}/").content.decode()


def test_paid_order_cannot_be_paid_again(client, customer, order):
    with pytest.raises(services.PaymentUnavailable):
        Order.objects.filter(pk=order.pk).update(status="paid")
        order.refresh_from_db()
        start(order)


def test_second_successful_payment_alerts_owner(client, order, demo_site):
    site_settings = SiteSettings.objects.get()
    site_settings.notify_email = "owner@example.com"
    site_settings.save()
    _, first = start(order)
    _, second = start(order)
    callback(client, first)
    callback(client, second)
    assert "پرداخت تکراری" in mail.outbox[-1].subject


def test_delivery_failure_keeps_the_money_and_retries(client, order):
    calls = []

    def flaky(sender, order, **kwargs):
        calls.append(order.pk)
        if len(calls) == 1:
            raise RuntimeError("receiver crashed")

    order_paid.connect(flaky)
    try:
        _, payment = start(order)
        assert callback(client, payment).status_code == 302  # the customer sees no crash
        order.refresh_from_db()
        assert order.status == "paid" and order.fulfilled_at is None
        assert services.reconcile() == 0
    finally:
        order_paid.disconnect(flaky)
    order.refresh_from_db()
    assert order.fulfilled_at and len(calls) == 2


def test_orders_are_private(client, order):
    stranger = get_user_model().objects.create_user("09351112233")
    client.force_login(stranger)
    assert client.get(f"/orders/{order.number}/").status_code == 404
    assert client.post(f"/payments/pay/{order.number}/").status_code == 404


def test_order_page_needs_login(client, order):
    response = client.get(f"/orders/{order.number}/")
    assert response.status_code == 302 and "/account/login/" in response.url


def test_panel_shows_orders_read_only(client, order):
    admin = get_user_model().objects.create_superuser("09120000000", password="x-pass-123")
    client.force_login(admin)
    assert order.number in client.get("/panel/orders/").content.decode()
    assert client.get(f"/panel/orders/edit/{order.pk}/").status_code in (302, 403)


# --- fake bank ----------------------------------------------------------------------


def test_fake_bank_full_round_trip(client, settings, customer, order):
    settings.PAYMENT_GATEWAY_ORDER = ["fake"]
    client.force_login(customer)
    bank_url = client.post(f"/payments/pay/{order.number}/").url
    assert client.get(bank_url).status_code == 200
    callback_url = client.post(bank_url, {"result": "ok"}).url
    assert client.get(callback_url).url == f"/orders/{order.number}/"
    order.refresh_from_db()
    assert order.status == "paid"


def test_fake_bank_cancel_leaves_order_unpaid(client, settings, customer, order):
    settings.PAYMENT_GATEWAY_ORDER = ["fake"]
    client.force_login(customer)
    bank_url = client.post(f"/payments/pay/{order.number}/").url
    client.get(client.post(bank_url, {"result": "fail"}).url)
    order.refresh_from_db()
    assert order.status == "pending" and order.payments.get().status == "failed"


def test_fake_bank_is_closed_unless_configured(client):
    assert client.get("/payments/fake/abc/").status_code == 404


def test_production_refuses_the_fake_gateway():
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.prod",
        "PAYMENT_GATEWAY_ORDER": "fake",
        "SECRET_KEY": "x",
        "DATABASE_URL": "sqlite:////tmp/x.db",
        "ALLOWED_HOSTS": "localhost",
    }
    code = "import django; django.setup()"
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode != 0
    assert "PAYMENT_GATEWAY_ORDER" in result.stderr


# --- real adapters, with no network (httpx MockTransport) --------------------------------


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def json_reply(payload):
    return lambda request: httpx.Response(200, json=payload)


def raises_network_error(request):
    raise httpx.ConnectError("no route")


def test_zarinpal_request_and_start_url():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"data": {"code": 100, "authority": "A0001"}, "errors": []})

    gateway = ZarinpalGateway(merchant_id="M", sandbox=False, client=client_for(handler))
    result = gateway.request(1000, "https://s/cb", "d", mobile="09121234567", order_id="1")
    assert seen["url"] == "https://payment.zarinpal.com/pg/v4/payment/request.json"
    assert result.authority == "A0001"
    assert result.redirect_url == "https://payment.zarinpal.com/pg/StartPay/A0001"


def test_zarinpal_sandbox_host():
    gateway = ZarinpalGateway(merchant_id="M", sandbox=True, client=client_for(json_reply({})))
    assert gateway.api.startswith("https://sandbox.zarinpal.com/")


@pytest.mark.parametrize("code", [100, 101])
def test_zarinpal_verify_ok(code):
    reply = {"data": {"code": code, "ref_id": 7, "card_pan": "5022****1"}, "errors": []}
    result = ZarinpalGateway("M", False, client_for(json_reply(reply))).verify("A", 1000)
    assert result.ok and result.ref_id == "7" and result.card_mask == "5022****1"


def test_zarinpal_verify_refused_is_a_definite_no():
    reply = {"data": [], "errors": {"code": -51, "message": "unpaid"}}
    assert not ZarinpalGateway("M", False, client_for(json_reply(reply))).verify("A", 1000).ok


def test_zarinpal_network_error_is_unknown():
    with pytest.raises(GatewayError):
        ZarinpalGateway("M", False, client_for(raises_network_error)).verify("A", 1000)


def test_zarinpal_refused_request():
    reply = {"data": [], "errors": {"code": -9}}
    with pytest.raises(GatewayError):
        ZarinpalGateway("M", False, client_for(json_reply(reply))).request(1, "u", "d")


def test_zarinpal_needs_merchant_id(settings):
    settings.ZARINPAL_MERCHANT_ID = ""
    with pytest.raises(GatewayError, match="MERCHANT"):
        ZarinpalGateway(sandbox=False, client=client_for(json_reply({}))).verify("A", 1)


def test_zibal_request_and_verify():
    gateway = ZibalGateway("zibal", client_for(json_reply({"result": 100, "trackId": 55})))
    assert gateway.request(1000, "u", "d").redirect_url == "https://gateway.zibal.ir/start/55"
    assert gateway.authority_from_callback({"trackId": "55", "success": "1"}) == "55"

    reply = {"result": 100, "amount": 1000, "refNumber": "R9", "cardNumber": "62****1"}
    result = ZibalGateway("zibal", client_for(json_reply(reply))).verify("55", 1000)
    assert result.ok and result.amount == 1000 and result.ref_id == "R9"


def test_zibal_verify_refused_and_network_error():
    assert not ZibalGateway("z", client_for(json_reply({"result": 202}))).verify("1", 1).ok
    with pytest.raises(GatewayError):
        ZibalGateway("z", client_for(raises_network_error)).verify("1", 1)
