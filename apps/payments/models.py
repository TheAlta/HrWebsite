from django.db import models
from django.db.models import Q

from apps.orders.models import Order


class Payment(models.Model):
    """One attempt to pay an order; an order may have several (spec section 7)."""

    class Status(models.TextChoices):
        INITIATED = "initiated", "در انتظار نتیجه درگاه"
        PAID = "paid", "موفق"
        FAILED = "failed", "ناموفق"

    order = models.ForeignKey(
        Order, verbose_name="سفارش", on_delete=models.PROTECT, related_name="payments"
    )
    gateway = models.CharField("درگاه", max_length=30)
    amount = models.BigIntegerField("مبلغ (ریال)")
    authority = models.CharField("شناسه پرداخت", max_length=100, blank=True, db_index=True)
    ref_id = models.CharField("کد پیگیری بانکی", max_length=100, blank=True)
    card_mask = models.CharField("کارت", max_length=30, blank=True)
    status = models.CharField(
        "وضعیت", max_length=20, choices=Status.choices, default=Status.INITIATED, db_index=True
    )
    raw_response = models.JSONField("پاسخ درگاه", default=dict, blank=True)
    created_at = models.DateTimeField("زمان شروع", auto_now_add=True, db_index=True)
    verified_at = models.DateTimeField("زمان تأیید", null=True, blank=True)

    class Meta:
        verbose_name = "پرداخت"
        verbose_name_plural = "پرداخت‌ها"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["gateway", "authority"],
                condition=~Q(authority=""),
                name="payment_unique_authority",
            )
        ]

    def __str__(self):
        return f"{self.order.number} / {self.gateway} / {self.get_status_display()}"
