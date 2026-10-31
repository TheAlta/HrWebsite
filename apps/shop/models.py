import secrets

from django import forms
from django.conf import settings
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.files.storage import storages
from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from wagtail.admin.forms import WagtailAdminModelForm
from wagtail.admin.panels import FieldPanel, FieldRowPanel, MultiFieldPanel
from wagtail.contrib.routable_page.models import RoutablePageMixin, path
from wagtail.fields import RichTextField

from apps.content.blocks import RICH_TEXT_FEATURES
from apps.content.models.base import BasePage
from apps.core import jalali
from apps.core.fields import MobileField
from apps.core.money import format_toman
from apps.core.text import to_en_digits
from apps.core.widgets import JalaliDateTimeInput
from apps.orders.models import Order


def private_storage():
    return storages["private"]


def normalize_code(code: str) -> str:
    return to_en_digits(code.strip()).upper()


class ProductQuerySet(models.QuerySet):
    def on_sale(self):
        return self.filter(is_active=True)


class ProductAdminForm(WagtailAdminModelForm):
    def save(self, commit=True):
        # Sales change the stock while this form is open; only an edit by the owner may set it
        if self.instance.pk and "stock" not in self.changed_data:
            self.instance.stock = Product.objects.values_list("stock", flat=True).get(
                pk=self.instance.pk
            )
        return super().save(commit)


class Product(models.Model):
    """A book or a file for sale (SHOP-1, SHOP-2).

    A plain model rather than a Wagtail page: publishing an old page revision would
    write an old stock number back.
    """

    class Kind(models.TextChoices):
        PHYSICAL = "physical", "کتاب چاپی"
        DIGITAL = "digital", "فایل دیجیتال"

    kind = models.CharField("نوع", max_length=20, choices=Kind.choices, default=Kind.PHYSICAL)
    title = models.CharField("عنوان", max_length=200)
    slug = models.SlugField(
        "نشانی",
        max_length=220,
        unique=True,
        blank=True,
        allow_unicode=True,
        help_text="اگر خالی بماند از عنوان ساخته می‌شود.",
    )
    cover_image = models.ForeignKey(
        "wagtailimages.Image",
        verbose_name="تصویر",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    summary = models.TextField("خلاصه", max_length=300, blank=True)
    description = RichTextField("معرفی", features=RICH_TEXT_FEATURES, blank=True)
    contents = RichTextField("فهرست مطالب", features=RICH_TEXT_FEATURES, blank=True)
    sample = models.ForeignKey(
        "wagtaildocs.Document",
        verbose_name="نمونه صفحات",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    price = models.BigIntegerField("قیمت (ریال)", default=0, help_text="به ریال. صفر یعنی رایگان.")
    stock = models.PositiveIntegerField("موجودی", default=0, help_text="فقط برای کتاب چاپی.")
    file = models.FileField(
        "فایل فروش",
        storage=private_storage,
        upload_to="products/",
        blank=True,
        help_text="فقط برای فایل دیجیتال. لینک عمومی ندارد. بدون انتخاب فایل، فایل قبلی می‌ماند.",
    )
    is_active = models.BooleanField("در حال فروش", default=True)
    sort_order = models.PositiveIntegerField("ترتیب", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ProductQuerySet.as_manager()

    base_form_class = ProductAdminForm
    panels = [
        FieldRowPanel([FieldPanel("title"), FieldPanel("kind")]),
        FieldPanel("slug"),
        FieldPanel("cover_image"),
        FieldPanel("summary"),
        FieldPanel("description"),
        FieldPanel("contents"),
        FieldPanel("sample"),
        MultiFieldPanel(
            [
                FieldRowPanel([FieldPanel("price"), FieldPanel("stock")]),
                # The default widget links to the current file, and this one has no public URL
                FieldPanel("file", widget=forms.FileInput),
            ],
            heading="فروش",
        ),
        FieldRowPanel([FieldPanel("is_active"), FieldPanel("sort_order")]),
    ]

    class Meta:
        verbose_name = "محصول"
        verbose_name_plural = "محصولات"
        ordering = ["sort_order", "-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug()
        super().save(*args, **kwargs)

    def clean(self):
        if self.price is not None and self.price < 0:
            raise ValidationError({"price": "قیمت نمی‌تواند منفی باشد."})
        if self.kind == self.Kind.DIGITAL and not self.file:
            raise ValidationError({"file": "برای فایل دیجیتال، فایل فروش را بارگذاری کنید."})

    def _unique_slug(self):
        base = slugify(self.title, allow_unicode=True) or "product"
        slug, number = base, 1
        while Product.objects.filter(slug=slug).exists():
            number += 1
            slug = f"{base}-{number}"
        return slug

    @property
    def is_digital(self):
        return self.kind == self.Kind.DIGITAL

    @property
    def in_stock(self):
        return self.is_digital or self.stock > 0

    @property
    def url(self):
        page = ShopPage.objects.live().first()
        return page.url + page.reverse_subpage("product", args=[self.slug]) if page else ""

    @admin.display(description="قیمت", ordering="price")
    def price_display(self):
        return format_toman(self.price) if self.price else "رایگان"


class ShopPage(RoutablePageMixin, BasePage):
    """/shop and /shop/{slug} (spec section 3)."""

    intro = RichTextField("مقدمه", features=["bold", "italic", "link"], blank=True)

    content_panels = [*BasePage.content_panels, FieldPanel("intro")]

    max_count = 1
    parent_page_types = ["content.HomePage"]
    subpage_types = []

    class Meta:
        verbose_name = "فروشگاه"

    def get_sitemap_urls(self, request=None):
        urls = super().get_sitemap_urls(request)
        for product in Product.objects.on_sale():
            urls.append(
                {
                    "location": self.get_full_url(request)
                    + self.reverse_subpage("product", args=[product.slug])
                }
            )
        return urls

    @path("")
    def index_route(self, request):
        products = Product.objects.on_sale().select_related("cover_image")
        return self.render(request, context_overrides={"products": products})

    # `str`, not `slug`: Persian slugs do not match Django's slug converter
    @path("<str:slug>/", name="product")
    def product_route(self, request, slug):
        from . import views

        return views.product(request, self, slug)


class Coupon(models.Model):
    """Discount code (SHOP-3).

    Kept here rather than in `orders` as the spec has it: `applies_to` needs products,
    and `orders` must not depend on the shop.
    """

    class Type(models.TextChoices):
        PERCENT = "percent", "درصدی"
        AMOUNT = "amount", "مبلغی"

    code = models.CharField("کد", max_length=40, unique=True)
    type = models.CharField("نوع", max_length=20, choices=Type.choices, default=Type.PERCENT)
    value = models.BigIntegerField("مقدار", help_text="درصد، یا مبلغ به ریال.")
    max_uses = models.PositiveIntegerField(
        "سقف کل استفاده", null=True, blank=True, help_text="خالی یعنی بدون سقف."
    )
    per_user_limit = models.PositiveIntegerField(
        "سقف برای هر کاربر", null=True, blank=True, default=1, help_text="خالی یعنی بدون سقف."
    )
    valid_from = models.DateTimeField("شروع اعتبار", null=True, blank=True)
    valid_to = models.DateTimeField("پایان اعتبار", null=True, blank=True)
    products = models.ManyToManyField(
        Product,
        verbose_name="محدود به محصولات",
        blank=True,
        help_text="اگر چیزی انتخاب نشود، روی همه محصولات اعمال می‌شود.",
    )
    is_active = models.BooleanField("فعال", default=True)

    panels = [
        FieldRowPanel([FieldPanel("code"), FieldPanel("is_active")]),
        FieldRowPanel([FieldPanel("type"), FieldPanel("value")]),
        FieldRowPanel([FieldPanel("max_uses"), FieldPanel("per_user_limit")]),
        FieldRowPanel(
            [
                FieldPanel("valid_from", widget=JalaliDateTimeInput),
                FieldPanel("valid_to", widget=JalaliDateTimeInput),
            ]
        ),
        FieldPanel("products"),
    ]

    class Meta:
        verbose_name = "کد تخفیف"
        verbose_name_plural = "کدهای تخفیف"
        ordering = ["-pk"]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = normalize_code(self.code)
        super().save(*args, **kwargs)

    def clean(self):
        self.code = normalize_code(self.code)
        if self.value is not None and self.value <= 0:
            raise ValidationError({"value": "مقدار باید بیشتر از صفر باشد."})
        if self.type == self.Type.PERCENT and self.value and self.value > 100:
            raise ValidationError({"value": "درصد تخفیف نمی‌تواند بیشتر از ۱۰۰ باشد."})
        if self.valid_from and self.valid_to and self.valid_from >= self.valid_to:
            raise ValidationError({"valid_to": "پایان اعتبار باید بعد از شروع باشد."})


class CouponUse(models.Model):
    """A discount given on an order. Cancelled orders give their use back."""

    coupon = models.ForeignKey(Coupon, on_delete=models.PROTECT, related_name="uses")
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="coupon_use")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "استفاده از کد تخفیف"
        verbose_name_plural = "استفاده از کدهای تخفیف"

    def __str__(self):
        return f"{self.coupon} — {self.order}"


class ShipmentAdminForm(WagtailAdminModelForm):
    NEXT_STATUS = {
        "preparing": "shipped",
        "shipped": "delivered",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = self.instance.status
        allowed = {current, self.NEXT_STATUS.get(current)}
        self.fields["status"].choices = [
            choice for choice in Shipment.Status.choices if choice[0] in allowed
        ]

    def clean(self):
        data = super().clean()
        if data.get("status") == Shipment.Status.SHIPPED and not data.get("tracking_code"):
            self.add_error("tracking_code", "برای ارسال، کد رهگیری را وارد کنید.")
        return data

    def save(self, commit=True):
        shipping_now = (
            "status" in self.changed_data and self.cleaned_data["status"] == Shipment.Status.SHIPPED
        )
        shipment = super().save(commit)
        if shipping_now:
            from . import services

            services.notify_shipped(shipment)
        return shipment


class Shipment(models.Model):
    """Delivery of the printed books of one order (spec section 8.4)."""

    class Status(models.TextChoices):
        AWAITING_PAYMENT = "awaiting_payment", "در انتظار پرداخت"
        PREPARING = "preparing", "در حال آماده‌سازی"
        SHIPPED = "shipped", "در حال ارسال"
        DELIVERED = "delivered", "تحویل شد"
        CANCELLED = "cancelled", "لغوشده"
        OUT_OF_STOCK = "out_of_stock", "پرداخت شد ولی موجودی نیست"

    order = models.OneToOneField(
        Order, verbose_name="سفارش", on_delete=models.CASCADE, related_name="shipment"
    )
    status = models.CharField(
        "وضعیت",
        max_length=20,
        choices=Status.choices,
        default=Status.AWAITING_PAYMENT,
        db_index=True,
    )
    recipient = models.CharField("گیرنده", max_length=120)
    mobile = MobileField("موبایل گیرنده")
    province = models.CharField("استان", max_length=60)
    city = models.CharField("شهر", max_length=60)
    address = models.TextField("نشانی")
    postal_code = models.CharField(
        "کد پستی", max_length=10, validators=[RegexValidator(r"^\d{10}$", "کد پستی ۱۰ رقم است.")]
    )
    tracking_code = models.CharField("کد رهگیری", max_length=40, blank=True)
    # Set when an unpaid order gave its stock back, so a late payment knows to take it again
    stock_released_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField("زمان ثبت", auto_now_add=True)

    base_form_class = ShipmentAdminForm
    panels = [
        FieldRowPanel([FieldPanel("status"), FieldPanel("tracking_code")]),
        MultiFieldPanel(
            [
                FieldPanel("order", read_only=True),
                FieldPanel("recipient", read_only=True),
                FieldPanel("mobile", read_only=True),
                FieldPanel("province", read_only=True),
                FieldPanel("city", read_only=True),
                FieldPanel("address", read_only=True),
                FieldPanel("postal_code", read_only=True),
            ],
            heading="مشخصات ارسال",
        ),
    ]

    class Meta:
        verbose_name = "ارسال"
        verbose_name_plural = "ارسال‌ها"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order} — {self.recipient}"

    @admin.display(description="زمان ثبت", ordering="created_at")
    def created_display(self):
        return jalali.format_datetime(self.created_at)


def new_token():
    return secrets.token_urlsafe(32)


class DownloadToken(models.Model):
    """A customer's right to download a bought file (SHOP-2, spec section 8.4)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="download_tokens"
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="download_tokens")
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="download_tokens")
    token = models.CharField(max_length=64, unique=True, default=new_token, editable=False)
    expires_at = models.DateTimeField()
    downloads_left = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "لینک دانلود"
        verbose_name_plural = "لینک‌های دانلود"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.product} — {self.user}"

    def get_absolute_url(self):
        return reverse("shop:download", args=[self.token])

    @property
    def is_valid(self):
        return self.downloads_left > 0 and self.expires_at > timezone.now()
