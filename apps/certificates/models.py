"""Certificates of attendance (EVT-5)."""

from django.conf import settings
from django.contrib import admin
from django.db import models
from wagtail.admin.panels import FieldPanel

from apps.core.admin_display import jalali_column
from apps.events.models import Registration


class Certificate(models.Model):
    """What a certificate says is copied when it is issued.

    A later edit to the event or to the profile never changes a document already
    handed out. The name is the one exception: if the profile had none, it is
    filled from the profile on the first download.
    """

    registration = models.OneToOneField(
        Registration,
        verbose_name="ثبت‌نام",
        on_delete=models.PROTECT,
        related_name="certificate",
    )
    code = models.CharField("کد استعلام", max_length=11, unique=True, editable=False)
    full_name = models.CharField(
        "نام روی گواهی",
        max_length=150,
        blank=True,
        help_text="اگر خالی باشد، با اولین دریافت از مشخصات کاربر پر می‌شود.",
    )
    event_title = models.CharField("رویداد", max_length=255, editable=False)
    event_kind = models.CharField("نوع رویداد", max_length=40, editable=False)
    instructor = models.CharField("مدرس", max_length=120, blank=True, editable=False)
    event_start = models.DateTimeField("شروع رویداد", editable=False)
    issued_at = models.DateTimeField("زمان صدور", auto_now_add=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="صادرکننده",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    revoked_at = models.DateTimeField("زمان ابطال", null=True, blank=True, editable=False)

    panels = [FieldPanel("full_name")]

    class Meta:
        verbose_name = "گواهی حضور"
        verbose_name_plural = "گواهی‌های حضور"
        ordering = ["-issued_at"]

    def __str__(self):
        return f"گواهی {self.code}"

    @property
    def is_valid(self):
        return self.revoked_at is None

    @admin.display(description="وضعیت")
    def status_display(self):
        return "معتبر" if self.is_valid else "باطل شده"

    @admin.display(description="نام", ordering="full_name")
    def name_display(self):
        return self.full_name or "— (از مشخصات کاربر)"

    issued_display = jalali_column("issued_at", "زمان صدور")
    revoked_display = jalali_column("revoked_at", "زمان ابطال")
    event_start_display = jalali_column("event_start", "شروع رویداد")
