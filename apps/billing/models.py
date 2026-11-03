from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from wagtail.admin.forms import WagtailAdminModelForm
from wagtail.admin.panels import FieldPanel, FieldRowPanel, InlinePanel
from wagtail.models import Orderable

from apps.core import jalali
from apps.core.admin_display import jalali_column, optional_column
from apps.core.fields import MobileField
from apps.core.money import format_rial
from apps.core.storage import private_storage
from apps.core.widgets import JalaliDateTimeInput
from apps.orders.models import Order


class Invoice(models.Model):
    """The sales document of a paid order (PAY-2).

    Numbers run 1, 2, 3 with no gaps, and an invoice is never deleted: a refunded
    order keeps its number and the invoice is marked void. Buyer and seller are
    copied, so later profile or settings changes never alter an issued invoice.
    """

    order = models.OneToOneField(
        Order, verbose_name="سفارش", on_delete=models.PROTECT, related_name="invoice"
    )
    number = models.PositiveIntegerField("شماره فاکتور", unique=True)
    issued_at = models.DateTimeField("تاریخ صدور", default=timezone.now)
    buyer_snapshot = models.JSONField("خریدار", default=dict)
    seller_snapshot = models.JSONField("فروشنده", default=dict)
    # Rendered on the first download and kept; emptied when the invoice is voided
    pdf_file = models.FileField(
        storage=private_storage, upload_to="invoices/", blank=True, editable=False
    )
    voided_at = models.DateTimeField("زمان ابطال", null=True, blank=True)

    class Meta:
        verbose_name = "فاکتور"
        verbose_name_plural = "فاکتورها"
        ordering = ["-number"]

    def __str__(self):
        return str(self.number)

    @property
    def is_void(self):
        return self.voided_at is not None

    @admin.display(description="تاریخ صدور", ordering="issued_at")
    def issued_display(self):
        return jalali.format_date(self.issued_at)

    @admin.display(description="مبلغ", ordering="order__total")
    def total_display(self):
        return format_rial(self.order.total)

    voided_display = jalali_column("voided_at", "زمان ابطال")

    @admin.display(description="خریدار")
    def buyer_display(self):
        return self.buyer_snapshot.get("name") or self.buyer_snapshot.get("mobile", "")


class ProFormaAdminForm(WagtailAdminModelForm):
    def clean(self):
        data = super().clean()
        if self.instance.pk and self.instance.status != ProForma.Status.DRAFT:
            raise ValidationError("پیش‌فاکتور ارسال‌شده قابل ویرایش نیست.")
        return data


class ProForma(ClusterableModel):
    """A price offer to an organization (PAY-3, spec section 8.5).

    Sending it creates the order, which is paid online from the link in the SMS,
    or recorded by hand when a transfer or cheque arrives.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        SENT = "sent", "ارسال‌شده"
        PAID = "paid", "پرداخت‌شده"
        CANCELLED = "cancelled", "لغوشده"

    organization = models.ForeignKey(
        "accounts.Organization",
        verbose_name="سازمان",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="proformas",
    )
    contact_name = models.CharField("نام رابط", max_length=120, blank=True)
    mobile = MobileField("موبایل رابط", help_text="لینک پرداخت به این شماره پیامک می‌شود.")
    valid_until = models.DateTimeField("اعتبار تا", null=True, blank=True)
    note = models.TextField("توضیح روی پیش‌فاکتور", blank=True)
    status = models.CharField(
        "وضعیت",
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        editable=False,
        db_index=True,
    )
    order = models.OneToOneField(
        Order,
        verbose_name="سفارش",
        null=True,
        blank=True,
        editable=False,
        on_delete=models.PROTECT,
        related_name="proforma",
    )
    created_at = models.DateTimeField("زمان ثبت", auto_now_add=True)

    base_form_class = ProFormaAdminForm
    panels = [
        FieldRowPanel([FieldPanel("organization"), FieldPanel("contact_name")]),
        FieldRowPanel(
            [FieldPanel("mobile"), FieldPanel("valid_until", widget=JalaliDateTimeInput)]
        ),
        InlinePanel("lines", heading="ردیف‌ها", label="ردیف", min_num=1),
        FieldPanel("note"),
    ]

    class Meta:
        verbose_name = "پیش‌فاکتور"
        verbose_name_plural = "پیش‌فاکتورها"
        ordering = ["-created_at"]

    def __str__(self):
        return f"پیش‌فاکتور {self.pk}"

    @property
    def total(self):
        return sum(line.line_total for line in self.lines.all())

    @admin.display(description="مبلغ")
    def total_display(self):
        return format_rial(self.total)

    @admin.display(description="زمان ثبت", ordering="created_at")
    def created_display(self):
        return jalali.format_date(self.created_at)

    organization_display = optional_column("organization", "سازمان")
    valid_until_display = jalali_column("valid_until", "اعتبار تا")
    order_display = optional_column("order", "سفارش")
    note_display = optional_column("note", "توضیح")


class ProFormaLine(Orderable):
    proforma = ParentalKey(ProForma, on_delete=models.CASCADE, related_name="lines")
    title = models.CharField("شرح", max_length=300)
    qty = models.PositiveIntegerField("تعداد", default=1)
    unit_price = models.BigIntegerField("قیمت واحد (ریال)")

    panels = [FieldPanel("title"), FieldRowPanel([FieldPanel("qty"), FieldPanel("unit_price")])]

    class Meta(Orderable.Meta):
        verbose_name = "ردیف پیش‌فاکتور"
        verbose_name_plural = "ردیف‌های پیش‌فاکتور"

    def __str__(self):
        return self.title

    def clean(self):
        if self.unit_price is not None and self.unit_price < 0:
            raise ValidationError({"unit_price": "قیمت نمی‌تواند منفی باشد."})

    @property
    def line_total(self):
        return self.unit_price * self.qty
