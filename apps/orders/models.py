from django.conf import settings
from django.contrib import admin
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.core.money import format_toman


class Order(models.Model):
    """The single purchase record for everything the site sells (spec section 7).

    Amounts are integer Rials. Booking, events and the shop create orders and
    listen to `order_paid`; this app knows nothing about them.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار پرداخت"
        PAID = "paid", "پرداخت‌شده"
        FAILED = "failed", "ناموفق"
        REFUNDED = "refunded", "بازگشت وجه"
        CANCELLED = "cancelled", "لغوشده"

    number = models.CharField("شماره سفارش", max_length=20, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="کاربر",
        on_delete=models.PROTECT,
        related_name="orders",
    )
    status = models.CharField(
        "وضعیت", max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    subtotal = models.BigIntegerField("جمع (ریال)", default=0)
    discount = models.BigIntegerField("تخفیف (ریال)", default=0)
    tax = models.BigIntegerField("مالیات (ریال)", default=0)
    total = models.BigIntegerField("مبلغ نهایی (ریال)", default=0)
    paid_at = models.DateTimeField("زمان پرداخت", null=True, blank=True)
    # Set after order_paid receivers finish; a paid order without it is retried
    fulfilled_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField("زمان ثبت", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "سفارش"
        verbose_name_plural = "سفارش‌ها"
        ordering = ["-created_at"]

    def __str__(self):
        return self.number

    @property
    def can_pay(self):
        return self.status == self.Status.PENDING and self.total > 0

    @admin.display(description="مبلغ", ordering="total")
    def total_display(self):
        return format_toman(self.total)


class OrderItem(models.Model):
    """One purchased thing. Title and price are copied, so later edits never change an order."""

    order = models.ForeignKey(
        Order, verbose_name="سفارش", on_delete=models.CASCADE, related_name="items"
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.PositiveBigIntegerField()
    item = GenericForeignKey("content_type", "object_id")
    title_snapshot = models.CharField("عنوان", max_length=300)
    unit_price = models.BigIntegerField("قیمت واحد (ریال)")
    qty = models.PositiveIntegerField("تعداد", default=1)

    class Meta:
        verbose_name = "قلم سفارش"
        verbose_name_plural = "اقلام سفارش"
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self):
        return self.title_snapshot

    @property
    def line_total(self):
        return self.unit_price * self.qty
