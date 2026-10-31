from django.conf import settings
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from modelcluster.fields import ParentalKey
from wagtail.admin.forms import WagtailAdminModelForm
from wagtail.admin.panels import FieldPanel, FieldRowPanel, InlinePanel, MultiFieldPanel
from wagtail.contrib.routable_page.models import RoutablePageMixin, path
from wagtail.fields import RichTextField
from wagtail.models import Orderable

from apps.content.blocks import RICH_TEXT_FEATURES
from apps.content.models.base import BasePage
from apps.core import jalali
from apps.core.embeds import parse_video_url
from apps.core.widgets import JalaliDateTimeInput
from apps.orders.models import Order


class EventIndexPage(BasePage):
    """/events — upcoming courses and webinars, as a list or a month (EVT-2)."""

    intro = RichTextField("مقدمه", features=["bold", "italic", "link"], blank=True)

    content_panels = [*BasePage.content_panels, FieldPanel("intro")]

    max_count = 1
    parent_page_types = ["content.HomePage"]
    subpage_types = ["events.EventPage"]

    class Meta:
        verbose_name = "آموزش و رویدادها"

    def get_context(self, request, *args, **kwargs):
        from . import calendar

        context = super().get_context(request, *args, **kwargs)
        context.update(calendar.index_context(self, request))
        return context


class EventPage(RoutablePageMixin, BasePage):
    """One course, webinar or talk (EVT-1).

    Seats are counted from `Registration` rows and never stored on the page, because
    republishing an old revision would write an old number back.
    """

    class Kind(models.TextChoices):
        COURSE = "course", "دوره"
        WEBINAR = "webinar", "وبینار"
        TALK = "talk", "سخنرانی"

    kind = models.CharField("نوع", max_length=20, choices=Kind.choices, default=Kind.COURSE)
    cover_image = models.ForeignKey(
        "wagtailimages.Image",
        verbose_name="تصویر",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    summary = models.TextField("خلاصه", max_length=300, blank=True)
    body = RichTextField("سرفصل‌ها و توضیحات", features=RICH_TEXT_FEATURES, blank=True)
    instructor = models.CharField("مدرس", max_length=120, blank=True)
    venue = models.CharField(
        "محل برگزاری", max_length=200, blank=True, help_text="برای برگزاری آنلاین خالی بماند."
    )
    start_at = models.DateTimeField("شروع", db_index=True)
    end_at = models.DateTimeField("پایان")
    capacity = models.PositiveIntegerField(
        "ظرفیت", null=True, blank=True, help_text="خالی یعنی بدون محدودیت."
    )
    price = models.BigIntegerField("قیمت (ریال)", default=0, help_text="به ریال. صفر یعنی رایگان.")
    join_link = models.URLField(
        "لینک کلاس", blank=True, help_text="فقط برای ثبت‌نام‌کنندگان نمایش داده می‌شود."
    )
    recording_url = models.URLField(
        "لینک ضبط",
        blank=True,
        help_text="بعد از پایان رویداد برای ثبت‌نام‌کنندگان پیامک می‌شود.",
    )
    video_url = models.URLField(
        "ویدئوی عمومی", blank=True, help_text="لینک آپارات یا یوتیوب. برای همه نمایش داده می‌شود."
    )

    content_panels = [
        *BasePage.content_panels,
        FieldRowPanel([FieldPanel("kind"), FieldPanel("instructor")]),
        FieldPanel("cover_image"),
        FieldPanel("summary"),
        FieldPanel("body"),
        MultiFieldPanel(
            [
                FieldRowPanel(
                    [
                        FieldPanel("start_at", widget=JalaliDateTimeInput),
                        FieldPanel("end_at", widget=JalaliDateTimeInput),
                    ]
                ),
                FieldPanel("venue"),
                InlinePanel("sessions", heading="جلسه‌ها", label="جلسه"),
            ],
            heading="زمان و مکان",
        ),
        FieldRowPanel([FieldPanel("capacity"), FieldPanel("price")], heading="ثبت‌نام"),
        MultiFieldPanel(
            [FieldPanel("join_link"), FieldPanel("recording_url"), FieldPanel("video_url")],
            heading="لینک‌ها",
        ),
    ]

    parent_page_types = ["events.EventIndexPage"]
    subpage_types = []

    class Meta:
        verbose_name = "رویداد"

    def clean(self):
        super().clean()
        if self.start_at and self.end_at and self.start_at >= self.end_at:
            raise ValidationError({"end_at": "پایان باید بعد از شروع باشد."})
        if self.price is not None and self.price < 0:
            raise ValidationError({"price": "قیمت نمی‌تواند منفی باشد."})
        if self.video_url and not parse_video_url(self.video_url):
            raise ValidationError({"video_url": "فقط لینک آپارات یا یوتیوب پشتیبانی می‌شود."})

    def get_share_image(self):
        return self.og_image or self.cover_image

    @property
    def is_free(self):
        return self.price == 0

    @property
    def video(self):
        return parse_video_url(self.video_url) if self.video_url else None

    @property
    def registration_open(self):
        return self.kind != self.Kind.TALK and timezone.now() < self.start_at

    @property
    def has_ended(self):
        return timezone.now() >= self.end_at

    def extra_jsonld(self, url):
        data = {
            "@context": "https://schema.org",
            "@type": "Event",
            "name": self.title,
            "description": self.search_description or self.summary,
            "url": url,
            "startDate": self.start_at.isoformat(),
            "endDate": self.end_at.isoformat(),
            "eventAttendanceMode": "https://schema.org/"
            + ("OfflineEventAttendanceMode" if self.venue else "OnlineEventAttendanceMode"),
        }
        if self.venue:
            data["location"] = {"@type": "Place", "name": self.venue, "address": self.venue}
        else:
            data["location"] = {"@type": "VirtualLocation", "url": url}
        return data

    def get_context(self, request, *args, **kwargs):
        from . import services

        context = super().get_context(request, *args, **kwargs)
        context["seats_left"] = services.seats_left(self)
        if request.user.is_authenticated:
            registration = services.active_registration(request.user, self)
            context["registration"] = registration
            context["has_seat"] = bool(registration and registration.is_confirmed)
        return context

    @path("")
    def detail_route(self, request):
        return self.render(request)

    @path("register/", name="register")
    def register_route(self, request):
        from . import views

        return views.register(request, self)


class EventSession(Orderable):
    """One meeting of a multi-session course (spec: `Event.sessions`)."""

    event = ParentalKey(EventPage, on_delete=models.CASCADE, related_name="sessions")
    title = models.CharField("عنوان جلسه", max_length=200, blank=True)
    start_at = models.DateTimeField("زمان")

    panels = [FieldPanel("title"), FieldPanel("start_at", widget=JalaliDateTimeInput)]

    class Meta(Orderable.Meta):
        verbose_name = "جلسه"
        verbose_name_plural = "جلسه‌ها"


class SpeakingPage(BasePage):
    """/speaking — past talks and the invitation form."""

    intro = RichTextField("مقدمه", features=["bold", "italic", "link"], blank=True)

    content_panels = [*BasePage.content_panels, FieldPanel("intro")]

    max_count = 1
    parent_page_types = ["content.HomePage"]
    subpage_types = []

    class Meta:
        verbose_name = "سخنرانی‌ها"

    def get_context(self, request, *args, **kwargs):
        from apps.crm.forms import SpeakingForm

        context = super().get_context(request, *args, **kwargs)
        context["talks"] = (
            EventPage.objects.live()
            .filter(kind=EventPage.Kind.TALK)
            .select_related("cover_image")
            .order_by("-start_at")
        )
        context["form"] = kwargs.get("form") or SpeakingForm()
        return context


class RegistrationAdminForm(WagtailAdminModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = self.instance.status
        allowed = {current}
        if current in Registration.ACTIVE_STATUSES:
            allowed.add(Registration.Status.CANCELLED)
        self.fields["status"].choices = [
            choice for choice in Registration.Status.choices if choice[0] in allowed
        ]

    def save(self, commit=True):
        # Cancelling here must free the seat and tell the customer, like the site does
        cancelling = (
            "status" in self.changed_data
            and self.cleaned_data["status"] == Registration.Status.CANCELLED
        )
        registration = super().save(commit=False)
        if cancelling:
            from . import services

            return services.cancel(Registration.objects.get(pk=registration.pk), by_owner=True)
        if commit:
            registration.save()
        return registration


class Registration(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار پرداخت"
        PAID = "paid", "قطعی"
        WAITLIST = "waitlist", "لیست انتظار"
        CANCELLED = "cancelled", "لغوشده"
        EXPIRED = "expired", "منقضی (پرداخت نشد)"

    ACTIVE_STATUSES = (Status.PENDING, Status.PAID, Status.WAITLIST)

    event = models.ForeignKey(
        EventPage, verbose_name="رویداد", on_delete=models.PROTECT, related_name="registrations"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="کاربر",
        on_delete=models.PROTECT,
        related_name="registrations",
    )
    status = models.CharField(
        "وضعیت", max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    order = models.ForeignKey(
        Order,
        verbose_name="سفارش",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="registrations",
    )
    # A pending seat belongs to the customer until this moment
    hold_expires_at = models.DateTimeField(null=True, blank=True, editable=False)
    reminded_1d_at = models.DateTimeField(null=True, blank=True, editable=False)
    reminded_30m_at = models.DateTimeField(null=True, blank=True, editable=False)
    recording_sent_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField("زمان ثبت", auto_now_add=True)

    base_form_class = RegistrationAdminForm
    panels = [FieldPanel("status")]

    class Meta:
        verbose_name = "ثبت‌نام"
        verbose_name_plural = "ثبت‌نام‌ها"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "user"],
                condition=Q(status__in=["pending", "paid", "waitlist"]),
                name="one_active_registration_per_event",
            )
        ]

    def __str__(self):
        return f"{self.event} — {self.user}"

    @property
    def is_confirmed(self):
        return self.status == self.Status.PAID

    @admin.display(description="زمان ثبت", ordering="created_at")
    def created_display(self):
        return jalali.format_datetime(self.created_at)
