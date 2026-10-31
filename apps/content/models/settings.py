from urllib.parse import quote

from django.db import models
from wagtail.admin.panels import FieldPanel, MultiFieldPanel, ObjectList, TabbedInterface
from wagtail.contrib.settings.models import BaseSiteSetting, register_setting
from wagtail.fields import StreamField
from wagtail.models import Site

from apps.core.fields import MobileField

from ..blocks import LinkBlock

SOCIAL_NETWORKS = [
    # (field, label)
    ("linkedin_url", "لینکدین"),
    ("instagram_url", "اینستاگرام"),
    ("telegram_url", "تلگرام"),
    ("bale_url", "بله"),
    ("aparat_url", "آپارات"),
    ("youtube_url", "یوتیوب"),
]


@register_setting(icon="cog")
class SiteSettings(BaseSiteSetting):
    """Site-wide values editable in the panel: Settings → تنظیمات سایت."""

    # Brand
    brand_name = models.CharField("نام برند", max_length=100, default="Arezoo")
    tagline = models.CharField("شعار", max_length=200, blank=True)
    logo = models.ForeignKey(
        "wagtailimages.Image",
        verbose_name="لوگو",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    # Contact
    phone = models.CharField("تلفن", max_length=30, blank=True)
    email = models.EmailField("ایمیل", blank=True)
    address = models.TextField("آدرس", blank=True)
    working_hours = models.CharField("ساعات کاری", max_length=200, blank=True)
    map_url = models.URLField("لینک نقشه", blank=True, help_text="لینک موقعیت در نشان یا گوگل‌مپ")
    whatsapp_number = MobileField("شماره واتساپ", blank=True)
    whatsapp_message = models.CharField(
        "پیام پیش‌فرض واتساپ", max_length=200, blank=True, default="سلام، برای مشاوره پیام می‌دهم."
    )

    # Social
    linkedin_url = models.URLField("لینکدین", blank=True)
    instagram_url = models.URLField("اینستاگرام", blank=True)
    telegram_url = models.URLField("تلگرام", blank=True)
    bale_url = models.URLField("بله", blank=True)
    aparat_url = models.URLField("آپارات", blank=True)
    youtube_url = models.URLField("یوتیوب", blank=True)

    # Navigation
    main_menu = StreamField([("link", LinkBlock())], blank=True, verbose_name="منوی اصلی")
    cta_label = models.CharField("متن دکمه برجسته", max_length=50, default="درخواست مشاوره")
    cta_page = models.ForeignKey(
        "wagtailcore.Page",
        verbose_name="صفحه دکمه برجسته",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    footer_text = models.TextField("متن فوتر", blank=True)
    trust_seal_html = models.TextField(
        "کد نماد اعتماد",
        blank=True,
        help_text="کد HTML اینماد. فقط کدی را که خود سامانه اینماد می‌دهد اینجا بگذارید.",
    )

    # Where new leads and follow-up reminders are sent (sprint 2)
    notify_email = models.EmailField(
        "ایمیل دریافت اعلان‌ها", blank=True, help_text="سرنخ‌های جدید و یادآورهای پیگیری"
    )
    notify_mobile = MobileField(
        "موبایل دریافت اعلان‌ها", blank=True, help_text="پیامک کوتاه برای هر سرنخ جدید"
    )

    # Shop (SHOP-1)
    shipping_fee = models.BigIntegerField(
        "هزینه ارسال (ریال)", default=0, help_text="مبلغ ثابت برای هر سفارش کتاب چاپی."
    )
    free_shipping_from = models.BigIntegerField(
        "ارسال رایگان از مبلغ (ریال)",
        null=True,
        blank=True,
        help_text="سفارش‌های بالای این مبلغ هزینه ارسال ندارند. خالی یعنی همیشه هزینه دارد.",
    )

    # SEO
    default_og_image = models.ForeignKey(
        "wagtailimages.Image",
        verbose_name="تصویر پیش‌فرض اشتراک‌گذاری",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="وقتی صفحه تصویر اختصاصی ندارد، در پیش‌نمایش لینکدین و تلگرام نمایش داده می‌شود.",
    )

    edit_handler = TabbedInterface(
        [
            ObjectList(
                [
                    FieldPanel("brand_name"),
                    FieldPanel("tagline"),
                    FieldPanel("logo"),
                    FieldPanel("default_og_image"),
                ],
                heading="برند",
            ),
            ObjectList(
                [
                    FieldPanel("phone"),
                    FieldPanel("email"),
                    FieldPanel("address"),
                    FieldPanel("working_hours"),
                    FieldPanel("map_url"),
                    MultiFieldPanel(
                        [FieldPanel("whatsapp_number"), FieldPanel("whatsapp_message")],
                        heading="واتساپ",
                    ),
                ],
                heading="تماس",
            ),
            ObjectList([FieldPanel(name) for name, _ in SOCIAL_NETWORKS], heading="شبکه‌ها"),
            ObjectList(
                [
                    FieldPanel("main_menu"),
                    MultiFieldPanel(
                        [FieldPanel("cta_label"), FieldPanel("cta_page")], heading="دکمه برجسته"
                    ),
                    FieldPanel("footer_text"),
                    FieldPanel("trust_seal_html"),
                ],
                heading="منو و فوتر",
            ),
            ObjectList(
                [FieldPanel("notify_email"), FieldPanel("notify_mobile")], heading="اعلان‌ها"
            ),
            ObjectList(
                [FieldPanel("shipping_fee"), FieldPanel("free_shipping_from")], heading="فروشگاه"
            ),
        ]
    )

    class Meta:
        verbose_name = "تنظیمات سایت"

    @classmethod
    def for_default_site(cls):
        """Settings outside a request (background tasks). None before a site exists."""
        site = Site.objects.filter(is_default_site=True).first()
        return cls.for_site(site) if site else None

    @property
    def whatsapp_url(self):
        if not self.whatsapp_number:
            return ""
        url = f"https://wa.me/98{self.whatsapp_number[1:]}"
        if self.whatsapp_message:
            url += f"?text={quote(self.whatsapp_message)}"
        return url

    @property
    def social_links(self):
        return [
            {"key": field.removesuffix("_url"), "label": label, "url": getattr(self, field)}
            for field, label in SOCIAL_NETWORKS
            if getattr(self, field)
        ]
