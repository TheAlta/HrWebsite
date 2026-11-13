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


# Icons the header's dropdown can show beside a link (templates/components/icon.html)
MENU_ICONS = [
    ("", "بدون آیکن"),
    ("briefcase", "کیف کار"),
    ("users", "افراد"),
    ("calendar", "تقویم"),
    ("newspaper", "مجله"),
    ("book", "کتاب"),
    ("award", "نشان"),
    ("mic", "میکروفون"),
    ("compass", "قطب‌نما"),
    ("route", "مسیر"),
]


class MenuItemBlock(LinkBlock):
    description = blocks.CharBlock(required=False, label="توضیح کوتاه", max_length=80)
    icon = blocks.ChoiceBlock(choices=MENU_ICONS, required=False, default="", label="آیکن")

    class Meta:
        icon = "link"
        value_class = LinkValue
        label = "لینک"


class MenuGroupBlock(blocks.StructBlock):
    """A menu entry that opens a short list of links, as in the owner's demo (REPORT #055)."""

    label = blocks.CharBlock(label="عنوان")
    links = blocks.ListBlock(MenuItemBlock(), min_num=1, label="لینک‌ها")

    class Meta:
        icon = "list-ul"
        label = "گروه کشویی"


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


class LeadMagnetBlock(blocks.StructBlock):
    """A file (catalog, CV) given in exchange for contact details (LEAD-4)."""

    title = blocks.CharBlock(default="دریافت کاتالوگ خدمات", label="عنوان")
    text = blocks.TextBlock(required=False, label="متن")
    document = DocumentChooserBlock(label="فایل")
    button_label = blocks.CharBlock(default="دریافت فایل", label="متن دکمه")

    def get_context(self, value, parent_context=None):
        from apps.crm.forms import DownloadForm

        context = super().get_context(value, parent_context)
        context["form"] = DownloadForm(initial={"document": value["document"].pk})
        return context

    class Meta:
        icon = "download"
        template = "blocks/lead_magnet.html"
        label = "فایل در ازای اطلاعات تماس"


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
    lead_magnet = LeadMagnetBlock()


# ---------- Home page sections (spec section 10, home page layout) ----------


class HeroBlock(blocks.StructBlock):
    """The demo's first section: the title with one underlined word, and a photo
    collage — a tilted frame, a sticker, a turning badge and the latest podcast."""

    eyebrow = blocks.CharBlock(
        required=False,
        label="برچسب بالای عنوان",
        help_text="مثل «مشاور منابع انسانی، مدرس و نویسنده»",
    )
    title = blocks.TextBlock(label="عنوان", rows=2, help_text="یک جمله ارزش.")
    highlight = blocks.CharBlock(
        required=False,
        label="کلمهٔ خط‌دار",
        help_text="یک کلمه از عنوان که زیرش خط طلایی می‌آید، مثل «آدم‌ها».",
    )
    quote = blocks.CharBlock(
        required=False,
        label="ادامهٔ رنگی عنوان",
        help_text="یک خط کوتاه زیر عنوان، به رنگ تأکید.",
    )
    subtitle = blocks.TextBlock(required=False, label="زیرعنوان")
    buttons = blocks.ListBlock(ButtonBlock(), max_num=2, label="دکمه‌ها")
    image = ImageChooserBlock(
        required=False,
        label="عکس دوربری‌شده",
        help_text=(
            "عکس با پس‌زمینهٔ شفاف (PNG یا WebP) که از قاب بیرون می‌زند."
            " خالی بگذارید تا تصویر هندسی نمایش داده شود."
        ),
    )
    photo_caption = blocks.CharBlock(required=False, label="زیرنویس عکس", max_length=60)
    sticker = blocks.CharBlock(
        required=False, default="سلام!", label="برچسب کنار عکس", max_length=12
    )
    badge_text = blocks.CharBlock(
        required=False,
        label="متن نشان چرخان",
        max_length=80,
        help_text="دور یک دایره می‌چرخد، مثل «چهارده سال تجربه ✳ مشاور ✳ مدرس ✳ نویسنده ✳»",
    )

    def get_context(self, value, parent_context=None):
        from .models import ArticleKind, ArticlePage

        context = super().get_context(value, parent_context)
        # The newest podcast episode, as a small card beside the photo
        context["episode"] = (
            ArticlePage.objects.live()
            .filter(kind=ArticleKind.PODCAST)
            .order_by("-first_published_at")
            .first()
        )
        return context

    class Meta:
        icon = "pick"
        template = "blocks/hero.html"
        label = "بخش اول (Hero)"


class ClientLogosBlock(blocks.StructBlock):
    """The demo's strip of client names, moving slowly sideways."""

    title = blocks.CharBlock(required=False, default="همکاری با", label="عنوان کوتاه")

    def get_context(self, value, parent_context=None):
        from apps.portfolio.models import Client

        context = super().get_context(value, parent_context)
        context["clients"] = Client.objects.filter(show_logo=True)
        return context

    class Meta:
        icon = "group"
        template = "blocks/client_logos.html"
        label = "نام مشتریان"


class PathLinkBlock(LinkBlock):
    note = blocks.CharBlock(required=False, label="توضیح کوتاه", max_length=40)

    class Meta:
        icon = "link"
        value_class = LinkValue
        label = "مسیر"


class IntroBlock(blocks.StructBlock):
    """«سلام، من … هستم»: a large greeting, a sentence whose bold words show as
    highlighter marks, and the paths a visitor can take (REPORT #058)."""

    title = blocks.CharBlock(label="عنوان", help_text="مثل «سلام، من آرزو هستم.»")
    highlight = blocks.CharBlock(
        required=False, label="کلمهٔ علامت‌دار", help_text="یک کلمه از عنوان با ماژیک طلایی."
    )
    text = blocks.RichTextBlock(
        features=["bold"],
        required=False,
        label="متن",
        help_text="بخش‌های پررنگ با ماژیک رنگی نمایش داده می‌شوند.",
    )
    paths = blocks.ListBlock(PathLinkBlock(), max_num=4, required=False, label="مسیرها")

    class Meta:
        icon = "user"
        template = "blocks/intro.html"
        label = "معرفی و مسیرها"


def consultation_topics():
    """The consultation form's topics, read late: crm's models import content."""
    from apps.crm.forms import TOPICS

    return TOPICS


class QuizQuestionBlock(blocks.StructBlock):
    question = blocks.CharBlock(label="سؤال")
    answers = blocks.ListBlock(
        blocks.CharBlock(label="پاسخ"),
        min_num=3,
        max_num=3,
        label="پاسخ‌ها",
        help_text="از ضعیف به قوی: پاسخ اول صفر امتیاز، دوم یک و سوم دو امتیاز.",
    )

    class Meta:
        icon = "help"
        label = "سؤال"


class QuizResultBlock(blocks.StructBlock):
    up_to = blocks.IntegerBlock(
        min_value=0,
        label="تا امتیاز",
        help_text="برای امتیازهای تا این عدد. بیشترین امتیاز دو برابر تعداد سؤال‌هاست.",
    )
    name = blocks.CharBlock(label="نام مرحله", help_text="مثل «مرحلهٔ نظم‌دهی»")
    text = blocks.TextBlock(label="توضیح")
    service = blocks.PageChooserBlock(
        page_type="content.ServicePage", required=False, label="خدمت پیشنهادی"
    )
    topic = blocks.ChoiceBlock(
        choices=consultation_topics,
        required=False,
        label="موضوع در فرم مشاوره",
        help_text="دکمهٔ نتیجه فرم مشاوره را با این موضوع باز می‌کند.",
    )

    class Meta:
        icon = "tick"
        label = "نتیجه"


class QuizBlock(blocks.StructBlock):
    """A short self-assessment: one question at a time, then a stage and a suggested
    service, and a button to the consultation form filled with it (REPORT #058)."""

    eyebrow = blocks.CharBlock(default="آماده‌اید برای", label="خط کوچک")
    big = blocks.CharBlock(default="سطح بعدی؟", label="کلمه‌های بزرگ")
    title = blocks.CharBlock(default="منابع انسانی سازمان شما در کدام مرحله است؟", label="عنوان")
    text = blocks.TextBlock(required=False, label="متن")
    button_label = blocks.CharBlock(
        default="کنجکاوید؟ آزمون را شروع کنید", label="متن دکمه", max_length=50
    )
    questions = blocks.ListBlock(QuizQuestionBlock(), min_num=1, max_num=10, label="سؤال‌ها")
    results = blocks.ListBlock(
        QuizResultBlock(),
        min_num=1,
        label="نتیجه‌ها",
        help_text="هر امتیاز به اولین نتیجه‌ای می‌رسد که «تا امتیاز» آن کمتر نباشد.",
    )

    def get_context(self, value, parent_context=None):
        from apps.crm.models import ConsultationPage

        context = super().get_context(value, parent_context)
        context["consultation"] = ConsultationPage.objects.live().first()
        context["results"] = sorted(value["results"], key=lambda result: result["up_to"])
        context["max_score"] = 2 * len(value["questions"])
        return context

    class Meta:
        icon = "help"
        template = "blocks/quiz.html"
        label = "آزمون کوتاه"


class NewsletterBlock(blocks.StructBlock):
    """The newsletter form as a page section, beside a turning badge."""

    title = blocks.CharBlock(default="نامه‌ای کوتاه، هر دو هفته یک بار", label="عنوان")
    text = blocks.TextBlock(required=False, label="متن")
    badge_text = blocks.CharBlock(required=False, label="متن نشان چرخان", max_length=80)

    class Meta:
        icon = "mail"
        template = "blocks/newsletter.html"
        label = "خبرنامه"


class ServicesBlock(blocks.StructBlock):
    title = blocks.CharBlock(
        required=False,
        default="خدمات",
        label="عنوان",
        help_text="بدون عنوان، کارت‌ها روی لبهٔ پایین بخش اول می‌نشینند.",
    )
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
    eyebrow = blocks.CharBlock(required=False, label="برچسب بالای عنوان")
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
    """The newest articles beside a stacked heading: a small line, the title, a coloured line."""

    eyebrow = blocks.CharBlock(required=False, label="خط کوچک بالای عنوان", help_text="مثل «نه یک»")
    title = blocks.CharBlock(default="از مجله", label="عنوان")
    tagline = blocks.CharBlock(
        required=False, label="خط رنگی زیر عنوان", help_text="مثل «معمولی منابع انسانی»"
    )
    intro = blocks.TextBlock(required=False, label="مقدمه")
    count = blocks.IntegerBlock(default=3, min_value=1, max_value=12, label="تعداد")

    def get_context(self, value, parent_context=None):
        from .models import ArticlePage, BlogIndexPage

        context = super().get_context(value, parent_context)
        context["articles"] = (
            ArticlePage.objects.live()
            .order_by("-first_published_at")
            .select_related("cover_image", "category")[: value["count"]]
        )
        context["blog"] = BlogIndexPage.objects.live().first()
        return context

    class Meta:
        icon = "doc-full"
        template = "blocks/latest_articles.html"
        label = "آخرین مطالب مجله"


class CallbackFormBlock(blocks.StructBlock):
    """«با من تماس بگیرید» form as a page section (LEAD-3)."""

    title = blocks.CharBlock(default="با من تماس بگیرید", label="عنوان")
    text = blocks.TextBlock(required=False, label="متن")

    def get_context(self, value, parent_context=None):
        from apps.crm.forms import CallbackForm

        context = super().get_context(value, parent_context)
        context["form"] = CallbackForm()
        return context

    class Meta:
        icon = "mobile-alt"
        template = "blocks/callback_form.html"
        label = "فرم درخواست تماس"


class RichTextSectionBlock(blocks.StructBlock):
    title = blocks.CharBlock(required=False, label="عنوان")
    body = blocks.RichTextBlock(features=RICH_TEXT_FEATURES, label="متن")

    class Meta:
        icon = "doc-full"
        template = "blocks/rich_text_section.html"
        label = "بخش متنی"


# Icons for the short traits beside the "about" picture (templates/components/icon.html)
TRAIT_ICONS = [
    ("heart", "دل"),
    ("message", "گفت‌وگو"),
    ("bulb", "ایده"),
    ("crown", "تاج"),
    ("users", "افراد"),
    ("award", "نشان"),
    ("compass", "قطب‌نما"),
    ("sprout", "رشد"),
]


class AboutBlock(blocks.StructBlock):
    """Short introduction beside a picture with a few traits, as in the owner's demo."""

    title = blocks.CharBlock(default="درباره من", label="عنوان")
    text = blocks.TextBlock(label="متن")
    button = blocks.ListBlock(ButtonBlock(), max_num=1, label="دکمه", required=False)
    traits = blocks.ListBlock(
        blocks.StructBlock(
            [
                ("label", blocks.CharBlock(label="عنوان", max_length=30)),
                ("icon", blocks.ChoiceBlock(choices=TRAIT_ICONS, default="heart", label="آیکن")),
            ]
        ),
        max_num=5,
        required=False,
        label="ویژگی‌ها",
        help_text="کلمه‌های کوتاه روی تصویر، مثل «همدلی».",
    )
    image = ImageChooserBlock(
        required=False,
        label="تصویر",
        help_text="خالی بگذارید تا تصویر نقاشی‌شده پیش‌فرض نمایش داده شود.",
    )

    class Meta:
        icon = "user"
        template = "blocks/about.html"
        label = "معرفی کوتاه"


class UpcomingEventBlock(blocks.StructBlock):
    """The next course or webinar with a countdown; hidden when none is ahead."""

    title = blocks.CharBlock(default="رویداد پیش رو", label="عنوان")
    button_label = blocks.CharBlock(default="ثبت‌نام", label="متن دکمه", max_length=40)

    def get_context(self, value, parent_context=None):
        from django.utils import timezone

        from apps.events import services as events
        from apps.events.models import EventIndexPage, EventPage

        context = super().get_context(value, parent_context)
        event = (
            EventPage.objects.live()
            .public()
            .exclude(kind=EventPage.Kind.TALK)
            .filter(start_at__gt=timezone.now())
            .order_by("start_at")
            .first()
        )
        context["event"] = event
        context["seats_left"] = events.seats_left(event) if event else None
        context["events_index"] = EventIndexPage.objects.live().first()
        return context

    class Meta:
        icon = "date"
        template = "blocks/upcoming_event.html"
        label = "رویداد پیش رو"


class ProductsBlock(blocks.StructBlock):
    """A row of books and files from the shop."""

    title = blocks.CharBlock(default="کتاب‌ها و منابع آموزشی", label="عنوان")
    intro = blocks.TextBlock(required=False, label="مقدمه")
    count = blocks.IntegerBlock(default=4, min_value=1, max_value=8, label="تعداد")

    def get_context(self, value, parent_context=None):
        from apps.shop.models import Product, ShopPage

        context = super().get_context(value, parent_context)
        context["shop"] = ShopPage.objects.live().first()
        context["products"] = (
            Product.objects.on_sale().select_related("cover_image")[: value["count"]]
            if context["shop"]
            else []
        )
        return context

    class Meta:
        icon = "doc-full-inverse"
        template = "blocks/products.html"
        label = "کتاب‌ها و محصولات"


class ContactBandBlock(blocks.StructBlock):
    """Two cards side by side: the call-back form and, optionally, a file to download."""

    callback_title = blocks.CharBlock(default="با من تماس بگیرید", label="عنوان فرم تماس")
    callback_text = blocks.TextBlock(required=False, label="متن فرم تماس")
    document = DocumentChooserBlock(required=False, label="فایل کنار فرم")
    document_title = blocks.CharBlock(default="کاتالوگ خدمات سازمانی", label="عنوان فایل")
    document_text = blocks.TextBlock(required=False, label="متن فایل")

    def get_context(self, value, parent_context=None):
        from apps.crm.forms import CallbackForm, DownloadForm

        context = super().get_context(value, parent_context)
        context["callback_form"] = CallbackForm()
        if value["document"]:
            context["download_form"] = DownloadForm(initial={"document": value["document"].pk})
        return context

    class Meta:
        icon = "mail"
        template = "blocks/contact_band.html"
        label = "فرم تماس و فایل"


class HomeBlock(blocks.StreamBlock):
    hero = HeroBlock()
    intro = IntroBlock()
    quiz = QuizBlock()
    newsletter = NewsletterBlock()
    about = AboutBlock()
    upcoming_event = UpcomingEventBlock()
    products = ProductsBlock()
    contact_band = ContactBandBlock()
    client_logos = ClientLogosBlock()
    services = ServicesBlock()
    stats = StatsBlock()
    testimonials = TestimonialsBlock()
    latest_articles = LatestArticlesBlock()
    cta = CallToActionBlock()
    text = RichTextSectionBlock()
    video = VideoBlock()
    faq = FAQBlock()
    callback_form = CallbackFormBlock()
    lead_magnet = LeadMagnetBlock()
