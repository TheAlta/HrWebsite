from django.core.exceptions import ValidationError
from django.db import models
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.blocks import CharBlock, StructBlock
from wagtail.fields import RichTextField, StreamField
from wagtail.search import index
from wagtail.snippets.models import register_snippet

from apps.core.embeds import parse_video_url

from ..blocks import RICH_TEXT_FEATURES, BodyBlock
from .base import BasePage


class AboutPage(BasePage):
    """«درباره من». Built so a team section can be switched on later (spec section 2)."""

    photo = models.ForeignKey(
        "wagtailimages.Image",
        verbose_name="عکس",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    headline = models.CharField("تیتر", max_length=200, blank=True)
    intro = RichTextField("معرفی کوتاه", features=["bold", "italic", "link"], blank=True)
    body = StreamField(BodyBlock(), blank=True, verbose_name="داستان و جزئیات")
    expertise = StreamField([("item", CharBlock(label="تخصص"))], blank=True, verbose_name="تخصص‌ها")
    credentials = StreamField(
        [
            (
                "credential",
                StructBlock(
                    [
                        ("title", CharBlock(label="عنوان مدرک")),
                        ("issuer", CharBlock(required=False, label="صادرکننده")),
                        ("year", CharBlock(required=False, label="سال")),
                    ],
                    label="مدرک",
                ),
            )
        ],
        blank=True,
        verbose_name="مدارک و گواهی‌ها",
    )
    resume = models.ForeignKey(
        "wagtaildocs.Document",
        verbose_name="رزومه (PDF)",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    intro_video_url = models.URLField("ویدئوی معرفی", blank=True, help_text="لینک آپارات یا یوتیوب")
    show_team = models.BooleanField("نمایش بخش تیم", default=False)

    content_panels = [
        *BasePage.content_panels,
        MultiFieldPanel(
            [FieldPanel("headline"), FieldPanel("photo"), FieldPanel("intro")], heading="معرفی"
        ),
        FieldPanel("body"),
        FieldPanel("expertise"),
        FieldPanel("credentials"),
        MultiFieldPanel(
            [FieldPanel("resume"), FieldPanel("intro_video_url")], heading="رزومه و ویدئو"
        ),
        FieldPanel("show_team"),
    ]

    max_count = 1
    parent_page_types = ["content.HomePage"]
    subpage_types = []

    class Meta:
        verbose_name = "درباره من"

    def clean(self):
        super().clean()
        if self.intro_video_url and not parse_video_url(self.intro_video_url):
            raise ValidationError({"intro_video_url": "فقط لینک آپارات یا یوتیوب پشتیبانی می‌شود."})

    @property
    def intro_video(self):
        return parse_video_url(self.intro_video_url) if self.intro_video_url else None

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["team"] = TeamMember.objects.filter(is_active=True) if self.show_team else []
        return context


@register_snippet
class TeamMember(index.Indexed, models.Model):
    name = models.CharField("نام", max_length=100)
    role = models.CharField("نقش", max_length=100, blank=True)
    photo = models.ForeignKey(
        "wagtailimages.Image",
        verbose_name="عکس",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    bio = models.TextField("معرفی", blank=True)
    is_active = models.BooleanField("فعال", default=True)
    sort_order = models.PositiveIntegerField("ترتیب", default=0)

    panels = [
        FieldPanel("name"),
        FieldPanel("role"),
        FieldPanel("photo"),
        FieldPanel("bio"),
        FieldPanel("is_active"),
        FieldPanel("sort_order"),
    ]
    search_fields = [index.SearchField("name"), index.AutocompleteField("name")]

    class Meta:
        verbose_name = "عضو تیم"
        verbose_name_plural = "اعضای تیم"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class ContactPage(BasePage):
    """Contact details come from Site Settings so they are edited in one place."""

    intro = RichTextField("مقدمه", features=["bold", "italic", "link"], blank=True)

    content_panels = [*BasePage.content_panels, FieldPanel("intro")]

    max_count = 1
    parent_page_types = ["content.HomePage"]
    subpage_types = []

    class Meta:
        verbose_name = "تماس"

    def get_context(self, request, *args, **kwargs):
        from apps.crm.forms import CallbackForm

        context = super().get_context(request, *args, **kwargs)
        context["callback_form"] = CallbackForm()
        return context


class LegalPage(BasePage):
    """Terms, privacy policy and similar text pages."""

    body = RichTextField("متن", features=RICH_TEXT_FEATURES)

    content_panels = [*BasePage.content_panels, FieldPanel("body")]
    search_fields = [*BasePage.search_fields, index.SearchField("body")]

    parent_page_types = ["content.HomePage"]
    subpage_types = []

    class Meta:
        verbose_name = "صفحه متنی (قوانین و ...)"
