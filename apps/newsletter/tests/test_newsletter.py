import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse

from apps.newsletter import services
from apps.newsletter.models import Campaign, Delivery, Subscriber
from apps.notifications.services import SMS_TOKEN20_WORDS
from apps.notifications.testing import CapturingSMS

pytestmark = pytest.mark.django_db

SUBSCRIBE = "/newsletter/subscribe/"


def post(client, htmx=True, **data):
    headers = {"HX-Request": "true"} if htmx else {}
    return client.post(SUBSCRIBE, data, headers=headers)


def test_footer_form_is_on_every_page(client, demo_site):
    assert reverse("newsletter:subscribe") in client.get("/").content.decode()


def test_subscribe_with_email_needs_consent(client):
    response = post(client, email="a@example.com")
    assert "این گزینه را تأیید کنید" in response.content.decode()
    assert not Subscriber.objects.exists()
    response = post(client, email="a@example.com", consent="on")
    assert "عضویت شما ثبت شد" in response.content.decode()
    subscriber = Subscriber.objects.get()
    assert (subscriber.email_ok, subscriber.sms_ok, subscriber.source) == (True, False, "footer")


def test_mobile_consent_is_for_sms_only(client):
    post(client, mobile="۰۹۱۲۱۲۳۴۵۶۷", consent="on")
    subscriber = Subscriber.objects.get()
    assert (subscriber.mobile, subscriber.sms_ok, subscriber.email_ok) == (
        "09121234567",
        True,
        False,
    )


def test_empty_form_asks_for_a_contact(client):
    response = post(client, consent="on")
    assert "ایمیل یا موبایل" in response.content.decode()


def test_bot_gets_thanks_and_nothing_is_saved(client):
    response = post(client, email="bot@example.com", consent="on", website="x")
    assert "عضویت شما ثبت شد" in response.content.decode()
    assert not Subscriber.objects.exists()


def test_rate_limit(client):
    for i in range(services.MAX_PER_IP):
        post(client, email=f"u{i}@example.com", consent="on")
    response = post(client, email="late@example.com", consent="on")
    assert "زیاد است" in response.content.decode()
    assert Subscriber.objects.count() == services.MAX_PER_IP


def test_without_javascript_a_page_shows_the_result(client, demo_site):
    response = post(client, htmx=False, email="a@example.com", consent="on")
    assert response.status_code == 200
    assert "<html" in response.content.decode()


def test_joining_twice_keeps_one_row_and_adds_the_channel():
    services.subscribe(email="A@example.com", source="footer")
    first = Subscriber.objects.get()
    services.unsubscribe(first)
    services.subscribe(email="a@example.com", mobile="09121234567", source="footer")
    subscriber = Subscriber.objects.get()
    assert (subscriber.email_ok, subscriber.sms_ok, subscriber.unsubscribed_at) == (
        True,
        True,
        None,
    )


def test_lead_with_marketing_consent_joins(client):
    client.post(
        reverse("crm:submit", args=["callback"]),
        {"name": "علی", "mobile": "09121234567", "marketing_consent": "on"},
    )
    client.post(reverse("crm:submit", args=["callback"]), {"name": "رضا", "mobile": "09351112233"})
    assert list(Subscriber.objects.values_list("mobile", "source")) == [("09121234567", "lead")]


def test_unsubscribe_link_asks_first_and_then_stops_everything(client):
    subscriber = services.subscribe(email="a@example.com", mobile="09121234567", source="footer")
    url = reverse("newsletter:unsubscribe", args=[subscriber.token])
    client.get(url)  # a mail scanner opening the link
    subscriber.refresh_from_db()
    assert subscriber.email_ok
    client.post(url)
    subscriber.refresh_from_db()
    assert not subscriber.email_ok and not subscriber.sms_ok
    assert client.get(reverse("newsletter:unsubscribe", args=["nope"])).status_code == 404


# --- sending ----------------------------------------------------------------------------


def test_email_campaign_reaches_only_email_consent_and_carries_the_link():
    services.subscribe(email="yes@example.com", source="footer")
    services.subscribe(mobile="09121234567", source="footer")
    gone = services.subscribe(email="gone@example.com", source="footer")
    services.unsubscribe(gone)
    campaign = Campaign.objects.create(title="خبر تازه", channel="email", body="متن خبر")
    assert services.queue(campaign) is True
    campaign.refresh_from_db()
    assert (campaign.status, campaign.sent_count) == (Campaign.Status.SENT, 1)
    assert [m.to for m in mail.outbox] == [["yes@example.com"]]
    token = Subscriber.objects.get(email="yes@example.com").token
    assert f"/newsletter/unsubscribe/{token}/" in mail.outbox[0].body


def test_sms_campaign_sends_a_short_token():
    services.subscribe(mobile="09121234567", source="footer")
    campaign = Campaign.objects.create(title="پیامک", channel="sms", body=" ".join(["کلمه"] * 20))
    services.queue(campaign)
    message = CapturingSMS.outbox[-1]
    assert message["template"] == "newsletter"
    assert len(message["params"]["token20"].split()) == SMS_TOKEN20_WORDS


def test_a_campaign_is_sent_once_even_if_the_task_runs_again():
    services.subscribe(email="a@example.com", source="footer")
    campaign = Campaign.objects.create(title="خبر", channel="email", body="متن")
    services.queue(campaign)
    assert services.queue(campaign) is False
    services.send_campaign(campaign.pk)  # a retried worker task
    assert len(mail.outbox) == 1
    assert Delivery.objects.count() == 1


# --- panel ------------------------------------------------------------------------------


@pytest.fixture
def admin_client(client):
    client.force_login(get_user_model().objects.create_superuser("09120000000", password="x"))
    return client


def test_panel_sends_a_campaign_after_showing_the_count(admin_client):
    services.subscribe(email="a@example.com", source="footer")
    campaign = Campaign.objects.create(title="خبر", channel="email", body="متن")
    inspect = reverse("panel_campaigns:inspect", args=[campaign.pk])
    send = reverse("panel_campaigns:send", args=[campaign.pk])
    assert send in admin_client.get(inspect).content.decode()
    assert "۱ نفر" in admin_client.get(send).content.decode()
    assert admin_client.post(send).status_code == 302
    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.SENT
    assert send not in admin_client.get(inspect).content.decode()


def test_panel_lists_and_has_no_manual_add(admin_client):
    services.subscribe(email="a@example.com", source="footer")
    assert admin_client.get(reverse("panel_subscribers:index")).status_code == 200
    assert admin_client.get(reverse("panel_subscribers:add")).status_code == 302
    assert admin_client.get(reverse("panel_campaigns:add")).status_code == 200
