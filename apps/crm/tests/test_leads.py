from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.utils import timezone
from wagtail.documents import get_document_model

from apps.content.models import SiteSettings
from apps.crm import services
from apps.crm.models import Lead, LeadNote, LeadStatus
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db

CALLBACK = {"name": "علي رضايي", "mobile": "۰۹۳۵ ۱۱۱ ۲۲۳۳"}
CONSULTATION = {
    "audience": "corporate",
    "topics": ["performance", "training"],
    "company": "شرکت نمونه",
    "company_size": "51-200",
    "timeframe": "asap",
    "name": "مدیر نمونه",
    "mobile": "09121112233",
    "marketing_consent": "on",
}
TRAINING = {
    "company": "سازمان نمونه",
    "topic": "مدیریت عملکرد",
    "headcount": "40",
    "delivery": "online",
    "name": "کارشناس",
    "mobile": "09121112244",
}


def post(client, kind, data, htmx=True):
    extra = {"HTTP_HX_REQUEST": "true"} if htmx else {}
    return client.post(f"/leads/{kind}/", data, **extra)


def test_callback_lead_is_saved_normalised_and_thanked(client, demo_site):
    response = post(client, "callback", CALLBACK)
    assert response.status_code == 200
    assert "درخواست شما ثبت شد" in response.content.decode()
    lead = Lead.objects.get()
    assert (lead.type, lead.status) == ("callback", LeadStatus.NEW)
    assert lead.name == "علی رضایی" and lead.mobile == "09351112233"
    sms = Notification.objects.get(to="09351112233")
    assert sms.template == "lead_received" and sms.params == {"token10": "علی"}


def test_consultation_payload_uses_readable_labels(client, demo_site):
    post(client, "consultation", CONSULTATION)
    lead = Lead.objects.get()
    assert lead.company == "شرکت نمونه" and lead.marketing_consent
    assert lead.payload == {
        "audience": "سازمانم",
        "topics": ["ارزیابی عملکرد", "آموزش و توسعه"],
        "company_size": "۵۱ تا ۲۰۰ نفر",
        "timeframe": "هرچه زودتر",
    }


def test_corporate_consultation_requires_company_and_reopens_that_step(client, demo_site):
    response = post(client, "consultation", {**CONSULTATION, "company": ""})
    html = response.content.decode()
    assert "نام سازمان را بنویسید" in html
    assert "step: 1," in html  # the «سازمان و زمان» step opens
    assert not Lead.objects.exists()


def test_corporate_training_lead(client, demo_site):
    post(client, "corporate_training", TRAINING)
    lead = Lead.objects.get()
    assert lead.type == "corporate_training"
    assert lead.payload["headcount"] == 40
    assert lead.payload["delivery"] == "آنلاین"


def test_download_needs_mobile_or_email_and_returns_the_file(client, demo_site):
    doc = get_document_model().objects.first()
    response = post(client, "download", {"name": "خواننده", "document": doc.pk})
    assert "موبایل یا ایمیل" in response.content.decode()
    response = post(
        client, "download", {"name": "خواننده", "email": "r@example.com", "document": doc.pk}
    )
    assert doc.url in response.content.decode()
    assert Lead.objects.get().payload == {"document": doc.title}


def test_download_without_javascript_redirects_to_file(client, demo_site):
    doc = get_document_model().objects.first()
    data = {"name": "خواننده", "email": "r@example.com", "document": doc.pk}
    response = post(client, "download", data, htmx=False)
    assert response.status_code == 302 and response.url == doc.url


def test_honeypot_saves_nothing(client, demo_site):
    response = post(client, "callback", {**CALLBACK, "website": "spam"})
    assert "درخواست شما ثبت شد" in response.content.decode()
    assert not Lead.objects.exists() and not Notification.objects.exists()


def test_rate_limit_per_ip(client, demo_site):
    for _ in range(services.MAX_LEADS_PER_IP):
        assert post(client, "callback", CALLBACK).status_code == 200
    response = post(client, "callback", CALLBACK)
    assert response.status_code == 429
    assert Lead.objects.count() == services.MAX_LEADS_PER_IP


def test_admin_is_notified_by_email_and_sms(client, demo_site):
    site_settings = SiteSettings.objects.get()
    site_settings.notify_email = "owner@example.com"
    site_settings.notify_mobile = "09120000001"
    site_settings.save()
    post(client, "consultation", CONSULTATION)
    lead = Lead.objects.get()
    assert mail.outbox[-1].to == ["owner@example.com"]
    body = mail.outbox[-1].body
    assert "مدیر نمونه" in body and "ارزیابی عملکرد" in body and f"/leads/edit/{lead.pk}/" in body
    admin_sms = Notification.objects.get(to="09120000001")
    assert admin_sms.params == {"token": str(lead.pk), "token10": "درخواست مشاوره"}


def test_utm_and_source_are_recorded(client, demo_site):
    client.get("/?utm_source=linkedin&utm_campaign=autumn")
    client.get("/?utm_source=google")  # first touch wins
    post(client, "callback", {**CALLBACK, "source": "/contact/"})
    lead = Lead.objects.get()
    assert lead.utm == {"utm_source": "linkedin", "utm_campaign": "autumn"}
    assert lead.source_url == "/contact/"


def test_success_without_javascript_shows_thank_you_page(client, demo_site):
    response = post(client, "callback", CALLBACK, htmx=False)
    assert response.status_code == 200
    assert (
        "<html" in response.content.decode() and "درخواست شما ثبت شد" in response.content.decode()
    )


def test_errors_without_javascript_render_consultation_page(client, demo_site):
    response = post(client, "consultation", {**CONSULTATION, "topics": []}, htmx=False)
    html = response.content.decode()
    assert "<html" in html and "درخواست مشاوره" in html and "field-error" in html


def test_unknown_kind_and_get_requests(client, demo_site):
    assert post(client, "nope", CALLBACK).status_code == 404
    assert client.get("/leads/callback/").status_code == 405


def test_forms_appear_on_pages(client, demo_site):
    assert 'action="/leads/consultation/"' in client.get("/consultation/").content.decode()
    assert 'action="/leads/callback/"' in client.get("/contact/").content.decode()
    assert 'action="/leads/callback/"' in client.get("/").content.decode()
    assert (
        'action="/leads/corporate_training/"' in client.get("/services/corporate/").content.decode()
    )
    assert 'action="/leads/download/"' in client.get("/about/").content.decode()


# --- follow-up reminders --------------------------------------------------------


def make_note(lead, minutes_from_now):
    return LeadNote.objects.create(
        lead=lead,
        text="تماس دوباره",
        follow_up_at=timezone.now() + timedelta(minutes=minutes_from_now),
    )


def test_due_reminders_are_emailed_once(client, demo_site):
    post(client, "callback", CALLBACK)
    lead = Lead.objects.get()
    due, later = make_note(lead, -5), make_note(lead, 60)
    site_settings = SiteSettings.objects.get()
    site_settings.notify_email = "owner@example.com"
    site_settings.save()

    assert services.send_followup_reminders() == 1
    assert "تماس دوباره" in mail.outbox[-1].body
    due.refresh_from_db()
    later.refresh_from_db()
    assert due.reminded_at and not later.reminded_at
    assert services.send_followup_reminders() == 0  # not repeated


def test_reminders_wait_until_an_email_is_set(client, demo_site):
    post(client, "callback", CALLBACK)
    note = make_note(Lead.objects.get(), -5)
    assert services.send_followup_reminders() == 0
    note.refresh_from_db()
    assert note.reminded_at is None  # will be sent once the address exists


# --- panel ------------------------------------------------------------------------


@pytest.fixture
def admin_client(client, demo_site):
    admin = get_user_model().objects.create_superuser("09120000000", password="x-pass-123")
    client.force_login(admin)
    return client


def test_panel_lists_and_exports_leads(admin_client):
    post(admin_client, "callback", CALLBACK)
    assert "علی رضایی" in admin_client.get("/panel/leads/").content.decode()
    response = admin_client.get("/panel/leads/?export=xlsx")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/vnd.openxmlformats")


def test_leads_cannot_be_added_by_hand(admin_client):
    assert admin_client.get("/panel/leads/new/").status_code in (302, 403)


def test_note_author_is_set_on_edit(admin_client):
    post(admin_client, "callback", CALLBACK)
    lead = Lead.objects.get()
    data = {
        "status": "contacted",
        "assigned_to": "",
        "name": lead.name,
        "mobile": lead.mobile,
        "email": "",
        "company": "",
        "notes-TOTAL_FORMS": "1",
        "notes-INITIAL_FORMS": "0",
        "notes-MIN_NUM_FORMS": "0",
        "notes-MAX_NUM_FORMS": "1000",
        "notes-0-text": "تماس گرفتم",
        "notes-0-follow_up_at": "",
        "notes-0-ORDER": "1",
        "notes-0-DELETE": "",
    }
    response = admin_client.post(f"/panel/leads/edit/{lead.pk}/", data)
    assert response.status_code == 302, response.content.decode()[:2000]
    lead.refresh_from_db()
    note = lead.notes.get()
    assert lead.status == "contacted"
    assert note.author.mobile == "09120000000"
