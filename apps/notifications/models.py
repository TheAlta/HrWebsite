from django.db import models


class Notification(models.Model):
    """Log of every SMS and email the site sends (spec section 7, notifications.Notification)."""

    class Channel(models.TextChoices):
        SMS = "sms", "پیامک"
        EMAIL = "email", "ایمیل"

    class Status(models.TextChoices):
        QUEUED = "queued", "در صف"
        SENT = "sent", "ارسال‌شده"
        FAILED = "failed", "ناموفق"

    channel = models.CharField("کانال", max_length=10, choices=Channel.choices, db_index=True)
    to = models.CharField("گیرنده", max_length=254, db_index=True)
    template = models.CharField(
        "الگو / موضوع", max_length=200, help_text="کلید الگوی پیامک یا موضوع ایمیل"
    )
    params = models.JSONField("پارامترها", default=dict, blank=True)
    body = models.TextField("متن", blank=True)
    status = models.CharField(
        "وضعیت", max_length=10, choices=Status.choices, default=Status.QUEUED, db_index=True
    )
    provider_message_id = models.CharField("شناسه ارائه‌دهنده", max_length=100, blank=True)
    error = models.TextField("خطا", blank=True)
    attempts = models.PositiveSmallIntegerField("تلاش‌ها", default=0)
    created_at = models.DateTimeField("ایجاد", auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField("ارسال", null=True, blank=True)

    class Meta:
        verbose_name = "پیام ارسالی"
        verbose_name_plural = "پیام‌های ارسالی"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_channel_display()} → {self.to}: {self.template}"
