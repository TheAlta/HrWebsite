"""Certificates of attendance (EVT-5).

The owner issues them from the panel after an event ends, unticking whoever did
not attend. Anyone holding a code can check it on the public verify page.
"""

import secrets

import segno
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.content.models import SiteSettings
from apps.core.http import absolute_url
from apps.core.pdf import render_pdf
from apps.core.text import to_en_digits
from apps.events.models import EventPage, Registration
from apps.notifications.services import send_sms, sms_words

from .models import Certificate

# No 0/O or 1/I, so a code read off paper is typed back right. Ten of 32 symbols
# is 50 bits: guessing a valid code by trying them is out of reach without a rate limit.
ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CODE_LENGTH = 10


class CertificateError(Exception):
    """A refused action, with a Persian message for the panel."""


def new_code() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
    return f"{raw[:5]}-{raw[5:]}"


def normalize_code(value: str) -> str:
    """What a person typed, in the stored form; empty if it cannot be a code."""
    raw = "".join(ch for ch in to_en_digits(value).upper() if ch in ALPHABET)
    return f"{raw[:5]}-{raw[5:]}" if len(raw) == CODE_LENGTH else ""


def lookup(value: str) -> Certificate | None:
    code = normalize_code(value)
    return Certificate.objects.filter(code=code).first() if code else None


def eligible(event: EventPage):
    """Confirmed attendees who have no certificate yet."""
    return (
        Registration.objects.filter(
            event=event, status=Registration.Status.PAID, certificate__isnull=True
        )
        .select_related("user")
        .order_by("user__last_name", "user__first_name", "pk")
    )


def can_issue(event: EventPage) -> bool:
    return event.issues_certificate and event.has_ended


def issue(event: EventPage, registrations, *, by=None) -> list[Certificate]:
    """Issue one certificate per registration and text each attendee."""
    if not event.issues_certificate:
        raise CertificateError("برای این رویداد گواهی حضور فعال نیست.")
    if not event.has_ended:
        raise CertificateError("گواهی حضور بعد از پایان رویداد صادر می‌شود.")
    pks = [registration.pk for registration in registrations]
    issued = []
    for registration in eligible(event).filter(pk__in=pks):
        certificate = _create(registration, event, by)
        if certificate:
            issued.append(certificate)
            send_sms(
                registration.user.mobile,
                "certificate_ready",
                {"token": certificate.code, "token20": sms_words(event.title)},
            )
    return issued


def _create(registration: Registration, event: EventPage, by) -> Certificate | None:
    """None if another staff member issued this one a moment earlier."""
    while True:
        try:
            with transaction.atomic():
                return Certificate.objects.create(
                    registration=registration,
                    code=new_code(),
                    full_name=registration.user.get_full_name(),
                    event_title=event.title,
                    event_kind=event.get_kind_display(),
                    instructor=event.instructor,
                    event_start=event.start_at,
                    issued_by=by,
                )
        except IntegrityError:
            if Certificate.objects.filter(registration=registration).exists():
                return None
            # otherwise the random code was already taken: draw another


def revoke(certificate: Certificate) -> None:
    updated = Certificate.objects.filter(pk=certificate.pk, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )
    if not updated:
        raise CertificateError("این گواهی قبلاً باطل شده است.")
    certificate.refresh_from_db()


def revoke_for_order(order) -> None:
    """A refunded registration loses its certificate (receiver of `order_reversed`)."""
    Certificate.objects.filter(registration__order=order, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )


def revoke_for_registration(registration: Registration) -> None:
    Certificate.objects.filter(registration=registration, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )


def fill_name(certificate: Certificate) -> str:
    """The name to print; taken from the profile once if it was empty when issued."""
    if not certificate.full_name:
        name = certificate.registration.user.get_full_name()
        if name:
            Certificate.objects.filter(pk=certificate.pk, full_name="").update(full_name=name)
            certificate.full_name = name
    return certificate.full_name


def verify_url(certificate: Certificate) -> str:
    return absolute_url(reverse("certificates:detail", args=[certificate.code]))


def certificate_pdf(certificate: Certificate) -> bytes:
    """Rendered each time from the stored text, so a new design applies to old ones."""
    url = verify_url(certificate)
    site_settings = SiteSettings.for_default_site()
    return render_pdf(
        "certificates/document.html",
        {
            "certificate": certificate,
            "verify_url": url,
            "qr": segno.make(url, error="m").svg_data_uri(scale=4, border=0, dark="#1c3970"),
            "brand_name": site_settings.brand_name if site_settings else "",
        },
    )
