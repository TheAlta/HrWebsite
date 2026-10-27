from django.conf import settings
from django.db import models
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from wagtail.admin.forms import WagtailAdminModelForm
from wagtail.admin.panels import FieldPanel, FieldRowPanel, InlinePanel, MultiFieldPanel
from wagtail.fields import RichTextField

from apps.content.models.base import BasePage
from apps.core.fields import MobileField


class LeadType(models.TextChoices):
    CONSULTATION = "consultation", "درخواست مشاوره"
    CORPORATE_TRAINING = "corporate_training", "آموزش سازمانی"
    CALLBACK = "callback", "درخواست تماس"
    DOWNLOAD = "download", "دانلود فایل"
    SPEAKING = "speaking", "دعوت به سخنرانی"


class LeadStatus(models.TextChoices):
    # Sales funnel from spec section 8.5
    NEW = "new", "جدید"
    CONTACTED = "contacted", "تماس گرفته شد"
    MEETING = "meeting", "جلسه اولیه"
    PROPOSAL = "proposal", "پیشنهاد ارسال شد"
    WON = "won", "برنده"
    LOST = "lost", "بازنده"


class LeadAdminForm(WagtailAdminModelForm):
    def save(self, commit=True):
        # Stamp the author on notes added in this edit
        for form in self.formsets["notes"].forms:
            if form.instance.pk is None and form.has_changed() and self.for_user:
                form.instance.author = self.for_user
        return super().save(commit)


class Lead(ClusterableModel):
    """Every form submission (LEAD-1..5). Form-specific answers live in `payload`."""

    type = models.CharField("نوع", max_length=30, choices=LeadType.choices, db_index=True)
    status = models.CharField(
        "وضعیت", max_length=20, choices=LeadStatus.choices, default=LeadStatus.NEW, db_index=True
    )
    name = models.CharField("نام", max_length=120)
    mobile = MobileField("موبایل", blank=True)
    email = models.EmailField("ایمیل", blank=True)
    company = models.CharField("سازمان", max_length=200, blank=True)
    payload = models.JSONField("جزئیات فرم", default=dict, blank=True)
    source_url = models.CharField("صفحه ارسال", max_length=500, blank=True)
    utm = models.JSONField("کمپین (UTM)", default=dict, blank=True)
    marketing_consent = models.BooleanField("رضایت پیامک/ایمیل تبلیغاتی", default=False)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="مسئول پیگیری",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_leads",
        limit_choices_to={"is_staff": True},
    )
    ip_hash = models.CharField(max_length=64, db_index=True, editable=False)
    created_at = models.DateTimeField("زمان ثبت", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("آخرین تغییر", auto_now=True)

    base_form_class = LeadAdminForm
    panels = [
        FieldRowPanel([FieldPanel("status"), FieldPanel("assigned_to")], heading="پیگیری"),
        MultiFieldPanel(
            [
                FieldPanel("type", read_only=True),
                FieldPanel("name"),
                FieldRowPanel([FieldPanel("mobile"), FieldPanel("email")]),
                FieldPanel("company"),
                FieldPanel("marketing_consent", read_only=True),
            ],
            heading="متقاضی",
        ),
        FieldPanel("payload", read_only=True),
        MultiFieldPanel(
            [FieldPanel("source_url", read_only=True), FieldPanel("utm", read_only=True)],
            heading="منبع",
            classname="collapsed",
        ),
        InlinePanel("notes", heading="یادداشت‌ها و یادآورها", label="یادداشت"),
    ]

    class Meta:
        verbose_name = "سرنخ"
        verbose_name_plural = "سرنخ‌ها"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} — {self.get_type_display()}"

    def payload_display(self):
        """Readable lines of the form answers, for emails and the panel."""
        from .forms import PAYLOAD_LABELS

        lines = []
        for key, value in self.payload.items():
            if isinstance(value, list):
                value = "، ".join(value)
            lines.append((PAYLOAD_LABELS.get(key, key), value))
        return lines


class LeadNote(models.Model):
    lead = ParentalKey(Lead, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, editable=False
    )
    text = models.TextField("یادداشت")
    follow_up_at = models.DateTimeField(
        "یادآوری در", null=True, blank=True, help_text="در این زمان ایمیل یادآوری می‌آید."
    )
    done = models.BooleanField("انجام شد", default=False)
    reminded_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    panels = [FieldPanel("text"), FieldRowPanel([FieldPanel("follow_up_at"), FieldPanel("done")])]

    class Meta:
        verbose_name = "یادداشت"
        verbose_name_plural = "یادداشت‌ها"
        ordering = ["created_at"]

    def __str__(self):
        return self.text[:50]


class ConsultationPage(BasePage):
    """/consultation — multi-step consultation request form (LEAD-1)."""

    intro = RichTextField("مقدمه", features=["bold", "italic", "link"], blank=True)
    thank_you_text = models.TextField(
        "پیام تشکر",
        default="درخواست شما ثبت شد. ظرف یک روز کاری با شما تماس می‌گیرم.",
    )

    content_panels = [*BasePage.content_panels, FieldPanel("intro"), FieldPanel("thank_you_text")]

    max_count = 1
    parent_page_types = ["content.HomePage"]
    subpage_types = []

    class Meta:
        verbose_name = "درخواست مشاوره"

    def get_context(self, request, *args, **kwargs):
        from .forms import ConsultationForm

        context = super().get_context(request, *args, **kwargs)
        context["form"] = kwargs.get("form") or ConsultationForm()
        return context
