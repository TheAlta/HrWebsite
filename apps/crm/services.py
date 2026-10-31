"""Lead capture and follow-up (LEAD-1..5, spec section 8.5)."""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from apps.content.models import SiteSettings
from apps.notifications.services import send_email, send_sms

from .models import Lead, LeadNote

RATE_WINDOW = timedelta(minutes=10)
MAX_LEADS_PER_IP = 5


class LeadRateLimited(Exception):
    pass


def create_lead(form, request, ip_hash: str) -> Lead:
    """Save a validated lead form and notify the applicant and the admin."""
    since = timezone.now() - RATE_WINDOW
    if Lead.objects.filter(ip_hash=ip_hash, created_at__gte=since).count() >= MAX_LEADS_PER_IP:
        raise LeadRateLimited

    data = form.cleaned_data
    lead = Lead.objects.create(
        type=form.lead_type,
        name=data["name"],
        mobile=data.get("mobile") or "",
        email=data.get("email") or "",
        company=data.get("company") or "",
        marketing_consent=data.get("marketing_consent", False),
        payload=form.payload(),
        source_url=(request.POST.get("source") or request.headers.get("referer", ""))[:500],
        utm=request.session.get("utm", {}),
        ip_hash=ip_hash,
    )
    notify_new_lead(lead, SiteSettings.for_request(request), request)
    return lead


def notify_new_lead(lead: Lead, site_settings, request=None):
    # Applicant: thank-you SMS (token10 may contain spaces — Kavenegar rule)
    if lead.mobile:
        send_sms(lead.mobile, "lead_received", {"token10": lead.name.split()[0]})

    # Admin: email with full details + short SMS
    if site_settings.notify_email:
        admin_url = (
            request.build_absolute_uri(lead_admin_url(lead)) if request else lead_admin_url(lead)
        )
        send_email(
            site_settings.notify_email,
            f"سرنخ جدید: {lead.get_type_display()} — {lead.name}",
            "crm/email/new_lead.txt",
            {"lead": lead, "admin_url": admin_url},
        )
    if site_settings.notify_mobile:
        send_sms(
            site_settings.notify_mobile,
            "lead_admin",
            {"token": str(lead.pk), "token10": lead.get_type_display()},
        )


def lead_admin_url(lead: Lead) -> str:
    return reverse("leads:edit", args=[lead.pk])


def send_followup_reminders() -> int:
    """Every 15 minutes: email the admin about notes whose follow-up time has come.

    A note is marked reminded only when the email was queued, so reminders are
    not lost while the notification address is still empty.
    """
    from wagtail.models import Site

    notes = list(
        LeadNote.objects.filter(
            done=False, reminded_at__isnull=True, follow_up_at__lte=timezone.now()
        ).select_related("lead")
    )
    site = Site.objects.filter(is_default_site=True).first()
    if not notes or site is None:
        return 0
    site_settings = SiteSettings.for_site(site)
    if not site_settings.notify_email:
        return 0

    send_email(
        site_settings.notify_email,
        f"یادآوری پیگیری: {len(notes)} مورد",
        "crm/email/followup_reminder.txt",
        {"notes": notes, "base_url": site.root_url.rstrip("/")},
    )
    LeadNote.objects.filter(pk__in=[n.pk for n in notes]).update(reminded_at=timezone.now())
    return len(notes)
