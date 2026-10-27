"""StreamField blocks shared by the home page, articles and other pages.

Each block renders through templates/blocks/<name>.html, so the UI sprint can
restyle a block without touching the page models.
"""

from django.core.exceptions import ValidationError
from wagtail import blocks
from wagtail.blocks.struct_block import StructBlockValidationError
from wagtail.documents.blocks import DocumentChooserBlock
from wagtail.images.blocks import ImageChooserBlock
from wagtail.snippets.blocks import SnippetChooserBlock

from apps.core.embeds import parse_video_url


class LinkValue(blocks.StructValue):
    @property
    def href(self):
        page = self.get("page")
        if page:
            return page.specific.url
        return self.get("url") or ""


class LinkBlock(blocks.StructBlock):
    """A label pointing either to an internal page or to an external URL."""

    label = blocks.CharBlock(label="عنوان")
    page = blocks.PageChooserBlock(required=False, label="صفحه داخلی")
    url = blocks.CharBlock(
        required=False, label="یا آدرس", help_text="آدرس کامل یا مسیر داخلی مثل /blog/"
    )

    def clean(self, value):
        value = super().clean(value)
        if bool(value.get("page")) == bool(value.get("url")):
            raise StructBlockValidationError(
                block_errors={"url": ValidationError("دقیقاً یکی از «صفحه» یا «آدرس» را پر کنید.")}
            )
        return value

    class Meta:
        icon = "link"
        value_class = LinkValue
        label = "لینک"


class ButtonBlock(LinkBlock):
    style = blocks.ChoiceBlock(
        choices=[("primary", "اصلی"), ("secondary", "ثانویه")],
        default="primary",
        label="سبک",
    )

    class Meta:
        icon = "pick"
        value_class = LinkValue
        label = "دکمه"


class VideoBlock(blocks.StructBlock):
    url = blocks.URLBlock(label="آدرس ویدئو", help_text="لینک آپارات یا یوتیوب")
    caption = blocks.CharBlock(required=False, label="توضیح")

    def clean(self, value):
        value = super().clean(value)
        if not parse_video_url(value["url"]):
            raise StructBlockValidationError(
                block_errors={"url": ValidationError("فقط لینک آپارات یا یوتیوب پشتیبانی می‌شود.")}
            )
        return value

    def get_context(self, value, parent_context=None):
        context = super().get_context(value, parent_context)
        context["embed"] = parse_video_url(value["url"])
        return context

    class Meta:
        icon = "media"
        template = "blocks/video.html"
        label = "ویدئو"


class ImageBlock(blocks.StructBlock):
    image = ImageChooserBlock(label="تصویر")
    caption = blocks.CharBlock(required=False, label="توضیح")

    class Meta:
        icon = "image"
        template = "blocks/image.html"
        label = "تصویر"


class QuoteBlock(blocks.StructBlock):
    text = blocks.TextBlock(label="متن")
    author = blocks.CharBlock(required=False, label="گوینده")

    class Meta:
        icon = "openquote"
        template = "blocks/quote.html"
        label = "نقل‌قول"


class FAQBlock(blocks.StructBlock):
    title = blocks.CharBlock(required=False, default="سؤال‌های متداول", label="عنوان")
    items = blocks.ListBlock(
        blocks.StructBlock(
            [
                ("question", blocks.CharBlock(label="سؤال")),
                ("answer", blocks.RichTextBlock(features=["bold", "italic", "link"], label="پاسخ")),
            ]
        ),
        label="سؤال‌ها",
    )

    class Meta:
        icon = "help"
        template = "blocks/faq.html"
        label = "سؤال‌های متداول"


class CallToActionBlock(blocks.StructBlock):
    title = blocks.CharBlock(label="عنوان")
    text = blocks.TextBlock(required=False, label="متن")
    buttons = blocks.ListBlock(ButtonBlock(), max_num=2, label="دکمه‌ها")

    class Meta:
        icon = "pick"
        template = "blocks/cta.html"
        label = "فراخوان"


class DocumentBlock(blocks.StructBlock):
    document = DocumentChooserBlock(label="فایل")
    title = blocks.CharBlock(required=False, label="عنوان نمایشی")

    class Meta:
        icon = "doc-full"
        template = "blocks/document.html"
        label = "فایل پیوست"


RICH_TEXT_FEATURES = ["h2", "h3", "bold", "italic", "link", "ol", "ul", "hr", "document-link"]


class BodyBlock(blocks.StreamBlock):
    """Free-form content: articles, about page, service details."""

    heading = blocks.CharBlock(
        form_classname="title", icon="title", label="تیتر", template="blocks/heading.html"
    )
    paragraph = blocks.RichTextBlock(
        features=RICH_TEXT_FEATURES, label="متن", template="blocks/paragraph.html"
    )
    image = ImageBlock()
    video = VideoBlock()
    quote = QuoteBlock()
    faq = FAQBlock()
    document = DocumentBlock()
    cta = CallToActionBlock()


# ---------- Home page sections (spec section 10, home page layout) ----------


class HeroBlock(blocks.StructBlock):
    title = blocks.CharBlock(label="عنوان", help_text="یک جمله ارزش: چه مشکلی را حل می‌کنید")
    subtitle = blocks.TextBlock(required=False, label="زیرعنوان")
    image = ImageChooserBlock(required=False, label="عکس")
    buttons = blocks.ListBlock(ButtonBlock(), max_num=2, label="دکمه‌ها")

    class Meta:
        icon = "pick"
        template = "blocks/hero.html"
        label = "بخش اول (Hero)"


class ClientLogosBlock(blocks.StructBlock):
    title = blocks.CharBlock(
        required=False, default="سازمان‌هایی که با آن‌ها کار کرده‌ام", label="عنوان"
    )

    def get_context(self, value, parent_context=None):
        from apps.portfolio.models import Client

        context = super().get_context(value, parent_context)
        context["clients"] = Client.objects.filter(show_logo=True).exclude(logo=None)
        return context

    class Meta:
        icon = "group"
        template = "blocks/client_logos.html"
        label = "لوگوی مشتریان"


class ServicesBlock(blocks.StructBlock):
    title = blocks.CharBlock(default="خدمات", label="عنوان")
    intro = blocks.TextBlock(required=False, label="مقدمه")
    services = blocks.ListBlock(
        blocks.PageChooserBlock(page_type="content.ServicePage"),
        required=False,
        label="خدمات",
        help_text="خالی بگذارید تا خدمات منتخب به‌صورت خودکار نمایش داده شوند.",
    )

    def get_context(self, value, parent_context=None):
        from .models import ServicePage

        context = super().get_context(value, parent_context)
        chosen = [p.specific for p in value["services"] if p and p.live]
        context["services"] = chosen or list(
            ServicePage.objects.live().filter(is_featured=True)[:4]
        )
        return context

    class Meta:
        icon = "list-ul"
        template = "blocks/services.html"
        label = "خدمات"


class StatsBlock(blocks.StructBlock):
    title = blocks.CharBlock(required=False, label="عنوان")
    items = blocks.ListBlock(
        blocks.StructBlock(
            [
                ("value", blocks.CharBlock(label="عدد", help_text="مثل ۱۵+")),
                ("label", blocks.CharBlock(label="توضیح", help_text="مثل سال تجربه")),
            ]
        ),
        max_num=6,
        label="آمار",
    )

    class Meta:
        icon = "order"
        template = "blocks/stats.html"
        label = "عدد و رقم"


class TestimonialsBlock(blocks.StructBlock):
    title = blocks.CharBlock(default="نظر مشتریان", label="عنوان")
    testimonials = blocks.ListBlock(
        SnippetChooserBlock("portfolio.Testimonial"),
        required=False,
        label="نظرها",
        help_text="خالی بگذارید تا نظرهای منتخب به‌صورت خودکار نمایش داده شوند.",
    )

    def get_context(self, value, parent_context=None):
        from apps.portfolio.models import Testimonial

        context = super().get_context(value, parent_context)
        chosen = [t for t in value["testimonials"] if t and t.consent_received]
        context["testimonials"] = chosen or list(
            Testimonial.objects.visible().filter(is_featured=True)[:6]
        )
        return context

    class Meta:
        icon = "openquote"
        template = "blocks/testimonials.html"
        label = "نظر مشتریان"


class LatestArticlesBlock(blocks.StructBlock):
    title = blocks.CharBlock(default="از مجله", label="عنوان")
    count = blocks.IntegerBlock(default=3, min_value=1, max_value=12, label="تعداد")

    def get_context(self, value, parent_context=None):
        from .models import ArticlePage

        context = super().get_context(value, parent_context)
        context["articles"] = (
            ArticlePage.objects.live()
            .order_by("-first_published_at")
            .select_related("cover_image", "category")[: value["count"]]
        )
        return context

    class Meta:
        icon = "doc-full"
        template = "blocks/latest_articles.html"
        label = "آخرین مطالب مجله"


class RichTextSectionBlock(blocks.StructBlock):
    title = blocks.CharBlock(required=False, label="عنوان")
    body = blocks.RichTextBlock(features=RICH_TEXT_FEATURES, label="متن")

    class Meta:
        icon = "doc-full"
        template = "blocks/rich_text_section.html"
        label = "بخش متنی"


class HomeBlock(blocks.StreamBlock):
    hero = HeroBlock()
    client_logos = ClientLogosBlock()
    services = ServicesBlock()
    stats = StatsBlock()
    testimonials = TestimonialsBlock()
    latest_articles = LatestArticlesBlock()
    cta = CallToActionBlock()
    text = RichTextSectionBlock()
    video = VideoBlock()
    faq = FAQBlock()
