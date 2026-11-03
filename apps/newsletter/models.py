import secrets

from django.contrib import admin
from django.db import models
from django.db.models import Q
from wagtail.admin.panels import FieldPanel

from apps.core import jalali
from apps.core.fields import MobileField


def new_token():
    return secrets.token_urlsafe(24)


class Subscriber(models.Model):
    """Someone who agreed to receive news (LEAD-6). Consent is per channel (spec section 11)."""

    email = models.EmailField("ایمیل", blank=True)
    mobile = MobileField("موبایل", blank=True)
    email_ok = models.BooleanField("رضایت ایمیل", default=False)
    sms_ok = models.BooleanField("رضایت پیامک", default=False)
    source = models.CharField("منبع", max_length=30, editable=False)
    token = models.CharField(max_length=64, unique=True, default=new_token, editable=False)
    ip_hash = models.CharField(max_length=64, blank=True, editable=False, db_index=True)
    created_at = models.DateTimeField("زمان عضویت", auto_now_add=True)
    unsubscribed_at = models.DateTimeField("زمان لغو عضویت", null=True, blank=True)

    panels = [FieldPanel("email_ok"), FieldPanel("sms_ok")]

    class Meta:
        verbose_name = "عضو خبرنامه"
        verbose_name_plural = "اعضای خبرنامه"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["email"], condition=~Q(email=""), name="subscriber_unique_email"
            ),
            models.UniqueConstraint(
                fields=["mobile"], condition=~Q(mobile=""), name="subscriber_unique_mobile"
            ),
        ]

    def __str__(self):
        return self.email or self.mobile

    @admin.display(description="زمان عضویت", ordering="created_at")
    def created_display(self):
        return jalali.format_date(self.created_at)


class Campaign(models.Model):
    """One newsletter, sent once to everyone who agreed to its channel."""

    class Channel(models.TextChoices):
        EMAIL = "email", "ایمیل"
        SMS = "sms", "پیامک"

    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        SENDING = "sending", "در حال ارسال"
        SENT = "sent", "ارسال‌شده"

    title = models.CharField("عنوان", max_length=200, help_text="موضوع ایمیل.")
    channel = models.CharField("کانال", max_length=10, choices=Channel.choices)
    body = models.TextField(
        "متن",
        help_text="برای پیامک کوتاه بنویسید: فقط چند کلمه داخل الگوی تأییدشده پیامک قرار می‌گیرد.",
    )
    status = models.CharField(
        "وضعیت", max_length=10, choices=Status.choices, default=Status.DRAFT, editable=False
    )
    sent_count = models.PositiveIntegerField("تعداد ارسال", default=0, editable=False)
    created_at = models.DateTimeField("زمان ثبت", auto_now_add=True)
    sent_at = models.DateTimeField("زمان ارسال", null=True, blank=True, editable=False)

    panels = [FieldPanel("title"), FieldPanel("channel"), FieldPanel("body")]

    class Meta:
        verbose_name = "خبرنامه"
        verbose_name_plural = "خبرنامه‌ها"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Delivery(models.Model):
    """Marks a campaign as sent to one subscriber, so a rerun never sends twice."""

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="deliveries")
    subscriber = models.ForeignKey(Subscriber, on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["campaign", "subscriber"], name="one_delivery_each")
        ]

    def __str__(self):
        return f"{self.campaign} — {self.subscriber}"
