from django.conf import settings
from django.contrib import admin
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Func, Q
from wagtail.admin.forms import WagtailAdminModelForm
from wagtail.admin.panels import FieldPanel
from wagtail.contrib.routable_page.models import RoutablePageMixin, path
from wagtail.fields import RichTextField

from apps.content.models.base import BasePage
from apps.core import jalali
from apps.orders.models import Order


class TsTzRange(Func):
    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class SessionType(models.Model):
    """A kind of bookable session (BOOK-1)."""

    class Mode(models.TextChoices):
        ONLINE = "online", "آنلاین"
        IN_PERSON = "in_person", "حضوری"
        PHONE = "phone", "تلفنی"

    title = models.CharField("عنوان", max_length=150)
    description = models.TextField("توضیح", blank=True)
    mode = models.CharField("نحوه برگزاری", max_length=20, choices=Mode.choices)
    duration_min = models.PositiveIntegerField("مدت (دقیقه)", default=60)
    price = models.BigIntegerField("قیمت (ریال)", default=0, help_text="به ریال. صفر یعنی رایگان.")
    buffer_min = models.PositiveIntegerField(
        "فاصله بعد از جلسه (دقیقه)", default=15, help_text="زمان استراحت تا جلسه بعدی"
    )
    meeting_link = models.URLField(
        "لینک جلسه آنلاین", blank=True, help_text="اتاق ثابت اسکای‌روم یا گوگل‌میت"
    )
    is_active = models.BooleanField("فعال", default=True)
    sort_order = models.PositiveIntegerField("ترتیب", default=0)

    class Meta:
        verbose_name = "نوع جلسه"
        verbose_name_plural = "انواع جلسه"
        ordering = ["sort_order", "title"]

    def __str__(self):
        return self.title

    def clean(self):
        if self.price is not None and self.price < 0:
            raise ValidationError({"price": "قیمت نمی‌تواند منفی باشد."})
        if not self.duration_min:
            raise ValidationError({"duration_min": "مدت جلسه باید بیشتر از صفر باشد."})


class Availability(models.Model):
    """Weekly working hours (BOOK-2). Several rows per day allow a lunch break."""

    class Weekday(models.IntegerChoices):
        SATURDAY = 0, "شنبه"
        SUNDAY = 1, "یکشنبه"
        MONDAY = 2, "دوشنبه"
        TUESDAY = 3, "سه‌شنبه"
        WEDNESDAY = 4, "چهارشنبه"
        THURSDAY = 5, "پنجشنبه"
        FRIDAY = 6, "جمعه"

    weekday = models.PositiveSmallIntegerField("روز هفته", choices=Weekday.choices)
    start_time = models.TimeField("از ساعت")
    end_time = models.TimeField("تا ساعت")

    class Meta:
        verbose_name = "ساعت کاری"
        verbose_name_plural = "ساعات کاری"
        ordering = ["weekday", "start_time"]

    def __str__(self):
        return f"{self.get_weekday_display()} {self.start_time:%H:%M}-{self.end_time:%H:%M}"

    def clean(self):
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({"end_time": "پایان باید بعد از شروع باشد."})


class TimeOff(models.Model):
    """Leave and public holidays: no session can overlap these (BOOK-2)."""

    start = models.DateTimeField("از")
    end = models.DateTimeField("تا")
    reason = models.CharField("دلیل", max_length=200, blank=True)

    class Meta:
        verbose_name = "مرخصی یا تعطیلی"
        verbose_name_plural = "مرخصی و تعطیلی"
        ordering = ["-start"]

    def __str__(self):
        return self.reason or f"{self.start:%Y-%m-%d}"

    def clean(self):
        if self.start and self.end and self.start >= self.end:
            raise ValidationError({"end": "پایان باید بعد از شروع باشد."})


class BookingAdminForm(WagtailAdminModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only moves that cannot break the no-overlap rule: an ended booking stays ended
        if "status" in self.fields:
            current = self.instance.status
            allowed = {current, Booking.Status.CANCELLED, Booking.Status.DONE}
            if current in (Booking.Status.CANCELLED, Booking.Status.EXPIRED):
                allowed = {current}
            self.fields["status"].choices = [
                choice for choice in Booking.Status.choices if choice[0] in allowed
            ]

    def save(self, commit=True):
        # Cancelling in the panel must free the slot and tell the customer too
        cancelling = (
            "status" in self.changed_data
            and self.cleaned_data["status"] == Booking.Status.CANCELLED
        )
        booking = super().save(commit=False)
        if cancelling:
            from . import services

            booking.status = Booking.objects.get(pk=booking.pk).status
            services.cancel(booking, by_owner=True)
            return booking
        if commit:
            booking.save()
        return booking


class Booking(models.Model):
    class Status(models.TextChoices):
        HELD = "held", "قفل موقت تا پرداخت"
        CONFIRMED = "confirmed", "تأییدشده"
        CANCELLED = "cancelled", "لغوشده"
        EXPIRED = "expired", "منقضی (پرداخت نشد)"
        DONE = "done", "برگزارشده"

    ACTIVE_STATUSES = (Status.HELD, Status.CONFIRMED)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="کاربر",
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    session_type = models.ForeignKey(
        SessionType, verbose_name="نوع جلسه", on_delete=models.PROTECT, related_name="bookings"
    )
    start_at = models.DateTimeField("شروع", db_index=True)
    end_at = models.DateTimeField("پایان")
    # End of the session plus its buffer: the time nobody else can book
    blocked_until = models.DateTimeField(editable=False)
    status = models.CharField(
        "وضعیت", max_length=20, choices=Status.choices, default=Status.HELD, db_index=True
    )
    hold_expires_at = models.DateTimeField("انقضای قفل", null=True, blank=True, editable=False)
    meeting_link = models.URLField("لینک جلسه", blank=True)
    admin_note = models.TextField("یادداشت مدیر", blank=True)
    order = models.ForeignKey(
        Order,
        verbose_name="سفارش",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    reminded_24h_at = models.DateTimeField(null=True, blank=True, editable=False)
    reminded_1h_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField("زمان ثبت", auto_now_add=True)

    base_form_class = BookingAdminForm
    panels = [FieldPanel("status"), FieldPanel("meeting_link"), FieldPanel("admin_note")]

    class Meta:
        verbose_name = "رزرو"
        verbose_name_plural = "رزروها"
        ordering = ["-start_at"]
        constraints = [
            # The database itself refuses overlapping bookings, so two customers
            # who pay at the same moment can never get the same slot (spec section 7)
            ExclusionConstraint(
                name="booking_no_overlap",
                expressions=[(TsTzRange("start_at", "blocked_until"), RangeOperators.OVERLAPS)],
                condition=Q(status__in=["held", "confirmed"]),
            )
        ]

    def __str__(self):
        return f"{self.session_type} — {self.user}"

    @admin.display(description="زمان جلسه", ordering="start_at")
    def start_display(self):
        return jalali.format_datetime(self.start_at)


class BookingPage(RoutablePageMixin, BasePage):
    """/booking — choose a session type, a time, then pay (spec section 8.1)."""

    intro = RichTextField("مقدمه", features=["bold", "italic", "link"], blank=True)

    content_panels = [*BasePage.content_panels, FieldPanel("intro")]

    max_count = 1
    parent_page_types = ["content.HomePage"]
    subpage_types = []

    class Meta:
        verbose_name = "رزرو جلسه"

    @path("")
    def index_route(self, request):
        return self.render(
            request, context_overrides={"session_types": SessionType.objects.filter(is_active=True)}
        )

    @path("<int:type_id>/", name="slots")
    def slots_route(self, request, type_id):
        from . import views

        return views.slots(request, self, type_id)

    @path("<int:type_id>/confirm/", name="confirm")
    def confirm_route(self, request, type_id):
        from . import views

        return views.confirm(request, self, type_id)
