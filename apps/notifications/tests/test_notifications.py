import httpx
import pytest
from django.core import mail

from apps.notifications.models import Notification
from apps.notifications.providers import SMSError, SMSProvider, SMSResult
from apps.notifications.providers.kavenegar import KavenegarSMS
from apps.notifications.services import check_sms_volume, deliver, send_email, send_sms

pytestmark = pytest.mark.django_db


class FailingSMS(SMSProvider):
    def send_template(self, to, template, params):
        raise SMSError("provider down")


class RecordingSMS(SMSProvider):
    sent = []

    def send_template(self, to, template, params):
        self.sent.append((to, template, params))
        return SMSResult(message_id="m-1", raw={})


def test_sms_is_logged_and_delivered(settings):
    settings.SMS_PROVIDER = "apps.notifications.tests.test_notifications.RecordingSMS"
    settings.SMS_TEMPLATES = {"otp": "panel-otp"}
    RecordingSMS.sent.clear()

    n = send_sms("+98 912 123 4567", "otp", {"token": "12345"})  # tasks run inline in tests
    n.refresh_from_db()
    assert n.to == "09121234567"
    assert n.status == Notification.Status.SENT
    assert n.provider_message_id == "m-1"
    # The panel template name, not the code key, reaches the provider
    assert RecordingSMS.sent == [("09121234567", "panel-otp", {"token": "12345"})]


def test_unknown_template_key_is_a_programming_error():
    with pytest.raises(ValueError):
        send_sms("09121234567", "no-such-template")


def test_provider_failure_is_recorded(settings):
    settings.SMS_PROVIDER = "apps.notifications.tests.test_notifications.FailingSMS"
    n = send_sms("09121234567", "otp", {"token": "1"})
    n.refresh_from_db()
    assert n.status == Notification.Status.FAILED
    assert "provider down" in n.error
    assert n.attempts == 1


def test_deliver_never_sends_twice(settings):
    settings.SMS_PROVIDER = "apps.notifications.tests.test_notifications.RecordingSMS"
    RecordingSMS.sent.clear()
    n = send_sms("09121234567", "otp", {"token": "1"})
    assert deliver(n.pk) == "already sent"
    assert len(RecordingSMS.sent) == 1


def test_email_is_rendered_and_sent():
    n = send_email(
        "admin@example.com",
        "موضوع",
        "notifications/email/sms_volume_alert.txt",
        {"count": 5, "threshold": 3},
    )
    n.refresh_from_db()
    assert n.status == Notification.Status.SENT
    assert len(mail.outbox) == 1
    assert "5 پیامک" in mail.outbox[0].body


def test_sms_volume_alert(settings):
    settings.SMS_ALERT_PER_HOUR = 2
    settings.ALERT_EMAILS = ["ops@example.com"]
    send_sms("09121234567", "otp", {"token": "1"})
    assert check_sms_volume() == 1
    assert len(mail.outbox) == 0
    send_sms("09121234567", "otp", {"token": "2"})
    assert check_sms_volume() == 2
    assert mail.outbox[-1].to == ["ops@example.com"]


# --- Kavenegar adapter (no network: httpx MockTransport) -------------------------


def kavenegar(handler):
    return KavenegarSMS(api_key="KEY", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_kavenegar_success():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"return": {"status": 200}, "entries": [{"messageid": 99}]})

    result = kavenegar(handler).send_template("09121234567", "otp", {"token": "12345"})
    assert result.message_id == "99"
    assert "/v1/KEY/verify/lookup.json" in seen["url"]
    assert "receptor=09121234567" in seen["url"] and "token=12345" in seen["url"]


def test_kavenegar_error_status():
    provider = kavenegar(
        lambda r: httpx.Response(200, json={"return": {"status": 418, "message": "x"}})
    )
    with pytest.raises(SMSError, match="418"):
        provider.send_template("09121234567", "otp", {"token": "1"})


def test_kavenegar_network_error():
    def handler(request):
        raise httpx.ConnectError("no route")

    with pytest.raises(SMSError, match="unreachable"):
        kavenegar(handler).send_template("09121234567", "otp", {"token": "1"})


def test_kavenegar_rejects_spaces_in_short_tokens():
    with pytest.raises(SMSError, match="token10"):
        kavenegar(lambda r: None).send_template("09121234567", "t", {"token": "دو کلمه"})


def test_kavenegar_requires_api_key(settings):
    settings.KAVENEGAR_API_KEY = ""
    with pytest.raises(SMSError, match="API_KEY"):
        KavenegarSMS().send_template("09121234567", "t", {"token": "1"})
