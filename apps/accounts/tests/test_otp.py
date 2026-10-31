from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.accounts import services
from apps.accounts.models import OTPCode
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db
MOBILE = "09121234567"


def last_code(mobile=MOBILE):
    from apps.notifications.testing import CapturingSMS

    return [m for m in CapturingSMS.outbox if m["to"] == mobile][-1]["params"]["token"]


def test_request_sends_a_hashed_five_digit_code():
    otp = services.request_code("+989121234567", "ip-1")
    code = last_code()
    assert len(code) == 5 and code.isdigit()
    assert code not in otp.code_hash  # only the HMAC is stored


def test_code_is_masked_in_the_message_log():
    services.request_code(MOBILE, "ip-1")
    logged = Notification.objects.get(to=MOBILE)
    assert logged.status == Notification.Status.SENT
    assert logged.params == {"token": "•••••"}


def test_correct_code_creates_the_user_once():
    services.request_code(MOBILE, "ip-1")
    user = services.verify_code(MOBILE, last_code())
    assert user.mobile == MOBILE
    assert not user.has_usable_password()
    services.request_code(MOBILE, "ip-1")
    assert services.verify_code(MOBILE, last_code()) == user
    assert get_user_model().objects.filter(mobile=MOBILE).count() == 1


def test_persian_digits_are_accepted():
    services.request_code(MOBILE, "ip-1")
    persian = last_code().translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    assert services.verify_code(MOBILE, persian).mobile == MOBILE


def test_code_cannot_be_reused():
    services.request_code(MOBILE, "ip-1")
    code = last_code()
    services.verify_code(MOBILE, code)
    with pytest.raises(services.OTPError):
        services.verify_code(MOBILE, code)


def test_wrong_code_counts_attempts_and_locks_after_five():
    services.request_code(MOBILE, "ip-1")
    code = last_code()
    wrong = "00000" if code != "00000" else "11111"
    for _ in range(services.MAX_ATTEMPTS):
        with pytest.raises(services.OTPError, match="درست نیست"):
            services.verify_code(MOBILE, wrong)
    with pytest.raises(services.OTPError, match="تلاش‌ها زیاد"):
        services.verify_code(MOBILE, code)  # even the right code is refused now


def test_expired_code_is_refused():
    services.request_code(MOBILE, "ip-1")
    OTPCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    with pytest.raises(services.OTPError, match="منقضی"):
        services.verify_code(MOBILE, last_code())


def test_new_code_invalidates_the_old_one():
    services.request_code(MOBILE, "ip-1")
    old = last_code()
    services.request_code(MOBILE, "ip-1")
    new = last_code()
    if old != new:
        with pytest.raises(services.OTPError):
            services.verify_code(MOBILE, old)
    assert services.verify_code(MOBILE, new)


def test_rate_limit_per_mobile():
    for _ in range(services.MAX_PER_MOBILE):
        services.request_code(MOBILE, "ip-1")
    with pytest.raises(services.OTPError, match="این شماره"):
        services.request_code(MOBILE, "ip-2")


def test_rate_limit_per_ip():
    for i in range(services.MAX_PER_IP):
        services.request_code(f"0912000{i:04d}", "same-ip")
    with pytest.raises(services.OTPError, match="شبکه شما"):
        services.request_code("09129999999", "same-ip")


# --- views ----------------------------------------------------------------------


def test_login_flow_with_htmx(client):
    response = client.post("/account/login/", {"mobile": MOBILE}, HTTP_HX_REQUEST="true")
    assert "کد تأیید" in response.content.decode()
    response = client.post(
        "/account/login/verify/",
        {"mobile": MOBILE, "code": last_code(), "next": "/blog/"},
        HTTP_HX_REQUEST="true",
    )
    assert response["HX-Redirect"] == "/blog/"
    assert client.get("/account/").status_code == 200


def test_login_flow_without_javascript(client):
    client.post("/account/login/", {"mobile": MOBILE})
    response = client.post("/account/login/verify/", {"mobile": MOBILE, "code": last_code()})
    assert response.status_code == 302
    assert response.url == "/account/"


def test_external_next_url_is_ignored(client):
    client.post("/account/login/", {"mobile": MOBILE})
    response = client.post(
        "/account/login/verify/",
        {"mobile": MOBILE, "code": last_code(), "next": "https://evil.example/"},
    )
    assert response.url == "/account/"


def test_wrong_code_shows_error(client):
    client.post("/account/login/", {"mobile": MOBILE})
    response = client.post("/account/login/verify/", {"mobile": MOBILE, "code": "99999"})
    assert response.status_code == 200
    assert "درست نیست" in response.content.decode() or "منقضی" in response.content.decode()


def test_invalid_mobile_shows_field_error(client):
    response = client.post("/account/login/", {"mobile": "123"})
    assert "شماره موبایل معتبر نیست" in response.content.decode()
    assert not Notification.objects.exists()


def test_account_requires_login_and_logout_works(client):
    assert client.get("/account/").status_code == 302
    user = get_user_model().objects.create_user(MOBILE)
    client.force_login(user)
    assert client.get("/account/").status_code == 200
    assert client.post("/account/logout/").status_code == 302
    assert client.get("/account/").status_code == 302
