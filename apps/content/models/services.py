from django.core.exceptions import ValidationError
from django.db import models
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.blocks import CharBlock
from wagtail.fields import RichTextField, StreamField
from wagtail.search import index

from ..blocks import BodyBlock
from .base import BasePage


class Audience(models.TextChoices):
    INDIVIDUAL = "individual", "فردی"
    CORPORATE = "corporate", "سازمانی"


class ServiceIndexPage(BasePage):
    """/services — lists individual and corporate services."""

    intro = RichTextField("مقدمه", features=["bold", "italic", "link"], blank=True)

    content_panels = [*BasePage.content_panels, FieldPanel("intro")]

    max_count = 1
    parent_page_types = ["content.HomePage"]
    subpage_types = ["content.ServicePage", "content.CorporateServicesPage"]

    class Meta:
        verbose_name = "فهرست خدمات"

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        services = ServicePage.objects.child_of(self).live().select_related("cover_image")
        context["individual_services"] = services.filter(audience=Audience.INDIVIDUAL)
        context["corporate_services"] = services.filter(audience=Audience.CORPORATE)
        context["corporate_page"] = CorporateServicesPage.objects.child_of(self).live().first()
        return context


class ServicePage(BasePage):
    """One service: problem, approach, outcome, duration, price or «استعلام»."""

    audience = models.CharField(
        "مخاطب", max_length=20, choices=Audience.choices, default=Audience.INDIVIDUAL
    )
    summary = models.TextField("خلاصه", max_length=300, help_text="در کارت خدمت نمایش داده می‌شود.")
    cover_image = models.ForeignKey(
        "wagtailimages.Image",
        verbose_name="تصویر",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    problem = RichTextField(
        "چه مسئله‌ای را حل می‌کند", features=["bold", "italic", "link", "ul"], blank=True
    )
    approach = RichTextField("روش کار", features=["bold", "italic", "link", "ul", "ol"], blank=True)
    deliverables = StreamField(
        [("item", CharBlock(label="خروجی"))], blank=True, verbose_name="خروجی‌ها"
    )
    duration = models.CharField(
        "مدت", max_length=100, blank=True, help_text="مثل «۴ جلسه ۹۰ دقیقه‌ای»"
    )
    # Integer Rials, never float (spec section 7); empty means "price on request"
    price = models.BigIntegerField(
        "قیمت (ریال)", null=True, blank=True, help_text="به ریال. خالی یعنی «استعلام قیمت»."
    )
    body = StreamField(BodyBlock(), blank=True, verbose_name="توضیحات بیشتر")
    testimonial = models.ForeignKey(
        "portfolio.Testimonial",
        verbose_name="نظر مشتری",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    case_study = models.ForeignKey(
        "portfolio.Project",
        verbose_name="نمونه موفق",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    is_featured = models.BooleanField("منتخب صفحه اصلی", default=False)

    content_panels = [
        *BasePage.content_panels,
        MultiFieldPanel(
            [
                FieldPanel("audience"),
                FieldPanel("summary"),
                FieldPanel("cover_image"),
                FieldPanel("is_featured"),
            ],
            heading="کارت خدمت",
        ),
        FieldPanel("problem"),
        FieldPanel("approach"),
        FieldPanel("deliverables"),
        MultiFieldPanel([FieldPanel("duration"), FieldPanel("price")], heading="مدت و قیمت"),
        FieldPanel("body"),
        MultiFieldPanel(
            [FieldPanel("testimonial"), FieldPanel("case_study")], heading="اعتمادسازی"
        ),
    ]
    search_fields = [*BasePage.search_fields, index.SearchField("summary")]

    parent_page_types = ["content.ServiceIndexPage"]
    subpage_types = []

    class Meta:
        verbose_name = "خدمت"
        verbose_name_plural = "خدمات"

    def clean(self):
        super().clean()
        if self.price is not None and self.price < 0:
            raise ValidationError({"price": "قیمت نمی‌تواند منفی باشد."})

    def get_share_image(self):
        return self.og_image or self.cover_image


class CorporateServicesPage(BasePage):
    """/services/corporate — the training request form arrives in sprint 2 (LEAD-2)."""

    intro = RichTextField("مقدمه", features=["bold", "italic", "link", "ul"], blank=True)
    body = StreamField(BodyBlock(), blank=True, verbose_name="توضیحات")

    content_panels = [*BasePage.content_panels, FieldPanel("intro"), FieldPanel("body")]

    max_count = 1
    parent_page_types = ["content.ServiceIndexPage"]
    subpage_types = []

    class Meta:
        verbose_name = "خدمات سازمانی"

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        from apps.crm.forms import CorporateTrainingForm

        context["training_form"] = CorporateTrainingForm()
        context["services"] = (
            ServicePage.objects.sibling_of(self)
            .live()
            .filter(audience=Audience.CORPORATE)
            .select_related("cover_image")
        )
        return context
