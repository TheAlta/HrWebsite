"""Panel hardening (spec section 11, REPORT #051): CSP, the second step, login limits."""

import re

import pytest
from axes.models import AccessAttempt
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.urls import reverse
from django_otp.oath import TOTP
from django_otp.plugins.otp_static.models import StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.roles import SUPPORT, setup_roles

pytestmark = pytest.mark.django_db

PANEL = "/panel/"
TWO_FACTOR = "/account/two-factor/"


@pytest.fixture
def staff(django_user_model):
    return django_user_model.objects.create_superuser("09120000000", password="right-password")


@pytest.fixture
def customer(django_user_model):
    return django_user_model.objects.create_user("09121234567")


@pytest.fixture
def required(settings):
    settings.PANEL_2FA_REQUIRED = True


def app_code(device: TOTPDevice, steps_ahead=0) -> str:
    """What the phone shows now, or a step later: a code is accepted only once."""
    totp = TOTP(device.bin_key, device.step, device.t0, device.digits, device.drift)
    totp.time += steps_ahead * device.step
    return f"{totp.token():06d}"


def set_up_app(client):
    """Go through the first visit and return the backup codes shown at the end."""
    client.get(TWO_FACTOR)
    device = TOTPDevice.objects.get()
    response = client.post(TWO_FACTOR, {"code": app_code(device), "next": PANEL})
    return re.findall(r"<li[^>]*>([a-z2-7]{8})</li>", response.content.decode())


# --- Content-Security-Policy ---------------------------------------------------------------


def test_the_site_runs_only_its_own_scripts(client, demo_site):
    policy = client.get("/")["Content-Security-Policy"]
    assert "script-src 'self';" in policy
    assert "unsafe-inline" not in policy.split("style-src-attr")[0]
    assert "unsafe-eval" not in policy
    assert "frame-ancestors 'none'" in policy
    assert "object-src 'none'" in policy
    assert "https://trustseal.enamad.ir" in policy  # the enamad seal in the footer


def test_site_pages_have_no_inline_script_or_handlers(client, demo_site):
    """What the strict policy would block; a new template must keep to it."""
    for url in ("/", "/about/", "/consultation/", "/booking/", "/events/", "/blog/post-1/"):
        html = client.get(url).content.decode()
        scripts = re.findall(r"<script(?![^>]*\bsrc=)(?![^>]*application/ld\+json)[^>]*>", html)
        assert scripts == [], url
        assert not re.search(r"\son[a-z]+=", html), url
        assert '"includeIndicatorStyles": false' in html


def test_the_panel_has_its_own_policy(client, staff):
    client.force_login(staff)
    policy = client.get(PANEL)["Content-Security-Policy"]
    assert "frame-ancestors 'self'" in policy  # page previews open inside the panel
    assert "script-src 'self' 'unsafe-inline'" in policy


def test_the_panel_does_not_call_wagtail_org(client, staff):
    client.force_login(staff)
    assert "releases.wagtail.org" not in client.get(PANEL).content.decode()


# --- the second step -----------------------------------------------------------------------


def test_off_the_panel_opens_after_login(client, staff):
    client.force_login(staff)
    assert client.get(PANEL).status_code == 200


def test_staff_without_an_app_are_sent_to_set_one_up(client, staff, required):
    client.force_login(staff)
    response = client.get(PANEL + "orders/")
    assert response.status_code == 302
    assert response.url == f"{TWO_FACTOR}?next=/panel/orders/"
    content = client.get(response.url).content.decode()
    assert "فعال کردن ورود دومرحله‌ای" in content
    assert "data:image/svg+xml" in content


def test_a_wrong_code_does_not_turn_it_on(client, staff, required):
    client.force_login(staff)
    client.get(TWO_FACTOR)
    response = client.post(TWO_FACTOR, {"code": "000000"})
    assert "کد درست نیست" in response.content.decode()
    assert not TOTPDevice.objects.get().confirmed
    assert client.get(PANEL).status_code == 302


def test_the_secret_stays_the_same_until_confirmed(client, staff, required):
    client.force_login(staff)
    client.get(TWO_FACTOR)
    client.get(TWO_FACTOR)
    assert TOTPDevice.objects.count() == 1


def test_setting_up_shows_backup_codes_once_and_opens_the_panel(client, staff, required):
    client.force_login(staff)
    codes = set_up_app(client)
    assert len(codes) == 10
    assert TOTPDevice.objects.get().confirmed
    assert client.get(PANEL).status_code == 200
    # the page is never stored by the browser
    assert "no-store" in client.get(TWO_FACTOR + "?next=/panel/")["Cache-Control"]


def test_each_new_login_asks_for_the_app_code(client, staff, required):
    client.force_login(staff)
    set_up_app(client)
    client.logout()
    client.force_login(staff)
    assert client.get(PANEL).status_code == 302
    content = client.get(TWO_FACTOR).content.decode()
    assert "کد ۶ رقمی اپ" in content
    assert "data:image/svg+xml" not in content  # no QR once set up

    device = TOTPDevice.objects.get()
    assert "کد درست نیست" in client.post(TWO_FACTOR, {"code": app_code(device)}).content.decode()
    device.refresh_from_db()
    device.throttling_failure_count = 0  # a person would wait the one second
    device.save()
    response = client.post(TWO_FACTOR, {"code": app_code(device, 1), "next": "/panel/orders/"})
    assert response.url == "/panel/orders/"
    assert client.get(PANEL).status_code == 200


def test_a_backup_code_works_once(client, staff, required):
    client.force_login(staff)
    [code, *_] = set_up_app(client)
    for expected in (True, False):
        client.logout()
        client.force_login(staff)
        client.post(TWO_FACTOR, {"code": code.upper()})
        assert (client.get(PANEL).status_code == 200) is expected
    assert StaticToken.objects.count() == 9


def test_the_next_address_must_be_on_this_site(client, staff, required):
    client.force_login(staff)
    client.get(TWO_FACTOR)
    response = client.post(
        TWO_FACTOR, {"code": app_code(TOTPDevice.objects.get()), "next": "https://evil.example/"}
    )
    assert "https://evil.example/" not in response.content.decode()
    assert reverse("wagtailadmin_home") in response.content.decode()


def test_support_staff_need_it_too(client, django_user_model, required):
    setup_roles()
    member = django_user_model.objects.create_user("09130000000")
    member.groups.add(Group.objects.get(name=SUPPORT))
    client.force_login(member)
    assert client.get(PANEL).url.startswith(TWO_FACTOR)


def test_customers_never_see_it(client, customer, required):
    client.force_login(customer)
    assert client.get(reverse("accounts:account")).status_code == 200
    assert client.get(TWO_FACTOR).url == reverse("accounts:account")
    assert not TOTPDevice.objects.exists()


def test_reset_for_a_lost_phone(client, staff, required, capsys):
    client.force_login(staff)
    set_up_app(client)
    call_command("reset_two_factor", "09120000000")
    assert not TOTPDevice.objects.exists()
    assert not StaticToken.objects.exists()
    client.logout()
    client.force_login(staff)
    assert "فعال کردن" in client.get(TWO_FACTOR).content.decode()


# --- login limits --------------------------------------------------------------------------


@pytest.fixture
def axes_on(settings):
    settings.AXES_ENABLED = True


def panel_login(client, password, ip="10.0.0.1"):
    return client.post(
        reverse("wagtailadmin_login"),
        {"username": "09120000000", "password": password},
        REMOTE_ADDR=ip,
    )


def test_five_wrong_passwords_close_the_login(client, staff, axes_on, demo_site):
    for _ in range(5):
        panel_login(client, "wrong")
    response = panel_login(client, "right-password")
    assert response.status_code == 429
    assert "ورود موقتاً بسته شد" in response.content.decode()
    assert "_auth_user_id" not in client.session


def test_another_address_is_not_locked_out(client, staff, axes_on):
    for _ in range(5):
        panel_login(client, "wrong")
    assert panel_login(client, "right-password", ip="10.0.0.2").status_code == 302


def test_a_right_password_resets_the_count(client, staff, axes_on):
    for _ in range(4):
        panel_login(client, "wrong")
    panel_login(client, "right-password")
    assert not AccessAttempt.objects.filter(failures_since_start__gt=0).exists()


def test_customer_sms_login_still_works_with_limits_on(client, axes_on, sms_outbox):
    client.post(reverse("accounts:login"), {"mobile": "09121234567"})
    code = sms_outbox[-1]["params"]["token"]
    client.post(reverse("accounts:verify"), {"mobile": "09121234567", "code": code})
    assert get_user_model().objects.get(mobile="09121234567").pk == int(
        client.session["_auth_user_id"]
    )


# --- the panel's history -------------------------------------------------------------------


def test_panel_actions_are_written_to_the_history(client, staff, customer):
    from django.db import transaction
    from wagtail.models import ModelLogEntry

    from apps.orders import services as orders
    from apps.orders.services import OrderLine

    order = orders.create_order(customer, [OrderLine(customer, "خدمت نمونه", 10_000_000)])
    with transaction.atomic():
        orders.mark_paid(order)
    client.force_login(staff)
    client.post(reverse("panel_orders:refund", args=[order.pk]), {"reference": "R-1"})

    entry = ModelLogEntry.objects.get(action="hrweb.refund")
    assert entry.object_id == str(order.pk)
    assert entry.user == staff
    assert (
        "ثبت بازگشت وجه"
        in client.get(reverse("wagtailadmin_reports:site_history")).content.decode()
    )


def test_a_refused_action_is_not_written(client, staff, customer):
    from wagtail.models import ModelLogEntry

    from apps.orders import services as orders
    from apps.orders.services import OrderLine

    order = orders.create_order(customer, [OrderLine(customer, "خدمت نمونه", 10_000_000)])
    client.force_login(staff)
    client.post(reverse("panel_orders:refund", args=[order.pk]))  # not paid: refused
    assert not ModelLogEntry.objects.filter(action="hrweb.refund").exists()
