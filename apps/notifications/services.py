"""Sending SMS and email (NTF-1, NTF-2).

Callers create a Notification row and the worker delivers it, so a slow
provider never blocks a page. This app knows nothing about leads, bookings
or orders — callers pass the recipient and template.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django_q.tasks import async_task

from apps.core.text import normalize_mobile

from .models import Notification
from .providers import SMSError, get_sms_provider

logger = logging.getLogger(__name__)


def send_sms(to: str, template_key: str, params: dict | None = None) -> Notification:
    """Queue a template SMS. `template_key` is a key of settings.SMS_TEMPLATES."""
    if template_key not in settings.SMS_TEMPLATES:
        raise ValueError(f"unknown SMS template key: {template_key}")
    notification = Notification.objects.create(
        channel=Notification.Channel.SMS,
        to=normalize_mobile(to),
        template=template_key,
        params=params or {},
    )
    async_task("apps.notifications.services.deliver", notification.pk)
    return notification


def send_email(to: str, subject: str, template_name: str, context: dict) -> Notification:
    """Queue a plain-text email rendered from `template_name`."""
    notification = Notification.objects.create(
        channel=Notification.Channel.EMAIL,
        to=to,
        template=subject,
        body=render_to_string(template_name, context).strip(),
    )
    async_task("apps.notifications.services.deliver", notification.pk)
    return notification


REDACTED = "•••••"


def _redact(notification):
    """Secrets (login codes) must not stay readable in the log after sending."""
    if notification.template in settings.SMS_SENSITIVE_TEMPLATES:
        notification.params = {key: REDACTED for key in notification.params}


def deliver(notification_id: int) -> str:
    """Worker task: send one queued notification and record the outcome."""
    notification = Notification.objects.get(pk=notification_id)
    if notification.status == Notification.Status.SENT:
        return "already sent"  # a re-queued task must not send twice

    notification.attempts += 1
    try:
        if notification.channel == Notification.Channel.SMS:
            result = get_sms_provider().send_template(
                notification.to,
                settings.SMS_TEMPLATES[notification.template],
                notification.params,
            )
            notification.provider_message_id = result.message_id
        else:
            send_mail(
                notification.template,
                notification.body,
                settings.DEFAULT_FROM_EMAIL,
                [notification.to],
            )
    except (SMSError, OSError) as exc:
        notification.status = Notification.Status.FAILED
        notification.error = str(exc)[:2000]
        _redact(notification)
        notification.save(update_fields=["status", "error", "attempts", "params"])
        logger.error("notification %s failed: %s", notification.pk, exc)
        return "failed"

    notification.status = Notification.Status.SENT
    notification.error = ""
    notification.sent_at = timezone.now()
    _redact(notification)
    notification.save(
        update_fields=["status", "error", "attempts", "sent_at", "provider_message_id", "params"]
    )
    return "sent"


def check_sms_volume() -> int:
    """Hourly: email ALERT_EMAILS when SMS volume is abnormal.

    Without captcha (REPORT #023) this is the early warning for OTP abuse,
    which costs money per message.
    """
    since = timezone.now() - timedelta(hours=1)
    count = Notification.objects.filter(
        channel=Notification.Channel.SMS, created_at__gte=since
    ).count()
    if count >= settings.SMS_ALERT_PER_HOUR and settings.ALERT_EMAILS:
        for email in settings.ALERT_EMAILS:
            send_email(
                email,
                "هشدار: تعداد پیامک‌های ارسالی غیرعادی است",
                "notifications/email/sms_volume_alert.txt",
                {"count": count, "threshold": settings.SMS_ALERT_PER_HOUR},
            )
    return count
