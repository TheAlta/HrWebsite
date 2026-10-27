from django.db import models
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.fields import RichTextField
from wagtail.search import index

from apps.content.models.base import BasePage

CONSENT_HELP = "فقط با رضایت مکتوب مشتری فعال شود (سند، بخش ۱۱)."


class Client(index.Indexed, models.Model):
    name = models.CharField("نام سازمان", max_length=150)
    logo = models.ForeignKey(
        "wagtailimages.Image",
        verbose_name="لوگو",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    website = models.URLField("وب‌سایت", blank=True)
    show_logo = models.BooleanField("نمایش لوگو در سایت", default=False, help_text=CONSENT_HELP)
    sort_order = models.PositiveIntegerField("ترتیب", default=0)

    panels = [
        FieldPanel("name"),
        FieldPanel("logo"),
        FieldPanel("website"),
        FieldPanel("show_logo"),
        FieldPanel("sort_order"),
    ]
    search_fields = [index.SearchField("name"), index.AutocompleteField("name")]

    class Meta:
        verbose_name = "مشتری"
        verbose_name_plural = "مشتریان"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class TestimonialQuerySet(models.QuerySet):
    def visible(self):
        """Only testimonials the client agreed to publish."""
        return self.filter(consent_received=True)


class Testimonial(index.Indexed, models.Model):
    author_name = models.CharField("نام", max_length=100)
    author_title = models.CharField("سمت", max_length=150, blank=True)
    client = models.ForeignKey(
        Client,
        verbose_name="سازمان",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="testimonials",
    )
    photo = models.ForeignKey(
        "wagtailimages.Image",
        verbose_name="عکس",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    quote = models.TextField("متن نظر")
    is_featured = models.BooleanField("منتخب", default=False)
    consent_received = models.BooleanField(
        "رضایت انتشار دارد", default=False, help_text=CONSENT_HELP
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TestimonialQuerySet.as_manager()

    panels = [
        FieldPanel("author_name"),
        FieldPanel("author_title"),
        FieldPanel("client"),
        FieldPanel("photo"),
        FieldPanel("quote"),
        MultiFieldPanel(
            [FieldPanel("is_featured"), FieldPanel("consent_received")], heading="انتشار"
        ),
    ]
    search_fields = [index.SearchField("author_name"), index.AutocompleteField("author_name")]

    class Meta:
        verbose_name = "نظر مشتری"
        verbose_name_plural = "نظرهای مشتریان"
        ordering = ["-is_featured", "-created_at"]

    def __str__(self):
        return f"{self.author_name} — {self.client or self.author_title}"


class Project(index.Indexed, models.Model):
    """A consulting engagement shown as a case study."""

    title = models.CharField("عنوان", max_length=200)
    client = models.ForeignKey(
        Client,
        verbose_name="مشتری",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="projects",
    )
    image = models.ForeignKey(
        "wagtailimages.Image",
        verbose_name="تصویر",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    summary = models.TextField("خلاصه", max_length=400)
    challenge = RichTextField("چالش", features=["bold", "italic", "ul"], blank=True)
    results = RichTextField("نتایج", features=["bold", "italic", "ul"], blank=True)
    year = models.CharField("سال", max_length=4, blank=True, help_text="مثل ۱۴۰۳")
    is_featured = models.BooleanField("منتخب", default=False)
    is_published = models.BooleanField("نمایش در سایت", default=True)
    sort_order = models.PositiveIntegerField("ترتیب", default=0)

    panels = [
        FieldPanel("title"),
        FieldPanel("client"),
        FieldPanel("image"),
        FieldPanel("summary"),
        FieldPanel("challenge"),
        FieldPanel("results"),
        FieldPanel("year"),
        MultiFieldPanel(
            [FieldPanel("is_published"), FieldPanel("is_featured"), FieldPanel("sort_order")],
            heading="انتشار",
        ),
    ]
    search_fields = [index.SearchField("title"), index.AutocompleteField("title")]

    class Meta:
        verbose_name = "پروژه"
        verbose_name_plural = "پروژه‌ها"
        ordering = ["sort_order", "-year", "title"]

    def __str__(self):
        return self.title


class PortfolioPage(BasePage):
    """/portfolio — projects, client logos and testimonials (spec section 2)."""

    intro = RichTextField("مقدمه", features=["bold", "italic", "link"], blank=True)

    content_panels = [*BasePage.content_panels, FieldPanel("intro")]

    max_count = 1
    parent_page_types = ["content.HomePage"]
    subpage_types = []

    class Meta:
        verbose_name = "نمونه‌کارها و مشتریان"

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["projects"] = Project.objects.filter(is_published=True).select_related(
            "client", "image"
        )
        context["clients"] = Client.objects.filter(show_logo=True).exclude(logo=None)
        context["testimonials"] = Testimonial.objects.visible().select_related("client", "photo")
        return context
