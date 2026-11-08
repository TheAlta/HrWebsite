"""Newsletter (LEAD-6): consent, unsubscribe, sending."""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from django_q.tasks import async_task
from wagtail.models import Site

from apps.notifications.services import send_email, send_sms, sms_words

from .models import Campaign, Delivery, Subscriber

RATE_WINDOW = timedelta(minutes=10)
MAX_PER_IP = 5


class RateLimited(Exception):
    pass


def subscribe(*, email="", mobile="", source, ip_hash="") -> Subscriber:
    """Record consent for each contact given. Joining again turns news back on."""
    if ip_hash:
        since = timezone.now() - RATE_WINDOW
        if Subscriber.objects.filter(ip_hash=ip_hash, created_at__gte=since).count() >= MAX_PER_IP:
            raise RateLimited
    subscriber = _find(email, mobile)
    if subscriber is None:
        try:
            with transaction.atomic():
                subscriber = Subscriber.objects.create(
                    email=email, mobile=mobile, source=source, ip_hash=ip_hash
                )
        except IntegrityError:  # the same person joined at the same moment
            subscriber = _find(email, mobile)
    subscriber.email = subscriber.email or email
    subscriber.mobile = subscriber.mobile or mobile
    subscriber.email_ok = subscriber.email_ok or bool(email)
    subscriber.sms_ok = subscriber.sms_ok or bool(mobile)
    subscriber.unsubscribed_at = None
    subscriber.save()
    return subscriber


def _find(email, mobile):
    if email:
        found = Subscriber.objects.filter(email__iexact=email).first()
        if found:
            return found
    if mobile:
        return Subscriber.objects.filter(mobile=mobile).first()
    return None


def unsubscribe(subscriber: Subscriber) -> None:
    Subscriber.objects.filter(pk=subscriber.pk).update(
        email_ok=False, sms_ok=False, unsubscribed_at=timezone.now()
    )


def audience(channel: str):
    if channel == Campaign.Channel.EMAIL:
        return Subscriber.objects.filter(email_ok=True).exclude(email="")
    return Subscriber.objects.filter(sms_ok=True).exclude(mobile="")


def queue(campaign: Campaign) -> bool:
    """Start sending in the background. A campaign is sent once."""
    started = Campaign.objects.filter(pk=campaign.pk, status=Campaign.Status.DRAFT).update(
        status=Campaign.Status.SENDING
    )
    if started:
        async_task("apps.newsletter.services.send_campaign", campaign.pk)
    return bool(started)


def send_campaign(campaign_id: int) -> int:
    """Worker task. Safe to run again after a crash: nobody gets it twice."""
    campaign = Campaign.objects.get(pk=campaign_id)
    base_url = _base_url()
    sent = 0
    for subscriber in audience(campaign.channel).iterator():
        try:
            with transaction.atomic():
                Delivery.objects.create(campaign=campaign, subscriber=subscriber)
                _send(campaign, subscriber, base_url)
        except IntegrityError:
            continue  # already sent in an earlier run
        sent += 1
    total = campaign.deliveries.count()
    Campaign.objects.filter(pk=campaign.pk).update(
        status=Campaign.Status.SENT, sent_count=total, sent_at=timezone.now()
    )
    return sent


def _send(campaign, subscriber, base_url):
    if campaign.channel == Campaign.Channel.EMAIL:
        send_email(
            subscriber.email,
            campaign.title,
            "newsletter/email/campaign.txt",
            {
                "campaign": campaign,
                "unsubscribe_url": base_url
                + reverse("newsletter:unsubscribe", args=[subscriber.token]),
            },
        )
    else:
        send_sms(subscriber.mobile, "newsletter", {"token20": sms_words(campaign.body)})


def _base_url():
    site = Site.objects.filter(is_default_site=True).first()
    return site.root_url if site else ""
