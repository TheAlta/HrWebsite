"""Numbers for the panel's home page and the sales report (ADM-1, ADM-2).

This app sits on top of the others: it reads every domain app and none reads it.
"""

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field

from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.booking.models import Booking
from apps.core import jalali
from apps.core.text import to_fa_digits
from apps.crm.models import Lead, LeadStatus
from apps.events.models import EventPage, Registration
from apps.orders.models import Order, OrderItem, Refund
from apps.shop.models import Shipment

SOLD = (Order.Status.PAID, Order.Status.REFUNDED)  # a refunded order was still a sale
DAILY_UP_TO_DAYS = 62  # longer ranges are grouped by Jalali month


def day_bounds(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    start = timezone.make_aware(dt.datetime.combine(day, dt.time.min))
    return start, start + dt.timedelta(days=1)


def new_leads():
    return Lead.objects.filter(status=LeadStatus.NEW)


def sessions_today_and_tomorrow():
    start, _ = day_bounds(timezone.localdate())
    return (
        Booking.objects.filter(
            status=Booking.Status.CONFIRMED,
            start_at__gte=start,
            start_at__lt=start + dt.timedelta(days=2),
        )
        .select_related("session_type", "user")
        .order_by("start_at")
    )


def upcoming_events(limit=3):
    taken = Q(registrations__status=Registration.Status.PAID) | Q(
        registrations__status=Registration.Status.PENDING,
        registrations__hold_expires_at__gt=timezone.now(),
    )
    return (
        EventPage.objects.live()
        .exclude(kind=EventPage.Kind.TALK)
        .filter(start_at__gt=timezone.now())
        .annotate(
            taken=Count("registrations", filter=taken),
            waiting=Count(
                "registrations", filter=Q(registrations__status=Registration.Status.WAITLIST)
            ),
        )
        .order_by("start_at")[:limit]
    )


def shipments_to_send():
    return Shipment.objects.filter(status=Shipment.Status.PREPARING)


@dataclass
class SalesReport:
    start: dt.datetime
    end: dt.datetime
    orders: list = field(default_factory=list)
    count: int = 0
    gross: int = 0
    discount: int = 0
    shipping: int = 0
    refunded: int = 0
    periods: list = field(default_factory=list)  # (label, count, total)
    by_kind: list = field(default_factory=list)  # (label, total)

    @property
    def net(self):
        return self.gross - self.refunded

    @property
    def last_moment(self):
        return self.end - dt.timedelta(minutes=1)


def sales(start: dt.datetime, end: dt.datetime) -> SalesReport:
    """Orders paid in [start, end), and refunds recorded in the same range."""
    rows = (
        Order.objects.filter(status__in=SOLD, paid_at__gte=start, paid_at__lt=end)
        .select_related("user")
        .prefetch_related("items")
        .order_by("paid_at")
    )
    report = SalesReport(start=start, end=end, orders=list(rows))
    totals = rows.aggregate(gross=Sum("total"), discount=Sum("discount"), shipping=Sum("shipping"))
    report.count = len(report.orders)
    report.gross = totals["gross"] or 0
    report.discount = totals["discount"] or 0
    report.shipping = totals["shipping"] or 0
    report.refunded = (
        Refund.objects.filter(created_at__gte=start, created_at__lt=end).aggregate(
            total=Sum("amount")
        )["total"]
        or 0
    )
    report.periods = _periods(report.orders, start, end)
    report.by_kind = _by_kind(report.orders)
    return report


def _periods(orders, start, end):
    monthly = (end - start).days > DAILY_UP_TO_DAYS
    buckets = defaultdict(lambda: [0, 0])
    for order in orders:
        local = jalali.to_jalali(order.paid_at)
        key = (local.year, local.month) if monthly else timezone.localtime(order.paid_at).date()
        buckets[key][0] += 1
        buckets[key][1] += order.total
    rows = []
    for key in sorted(buckets):
        label = f"{jalali.MONTHS[key[1] - 1]} {key[0]}" if monthly else jalali.format_date(key)
        rows.append((to_fa_digits(label), *buckets[key]))
    return rows


def _by_kind(orders):
    """Sales per kind of thing sold, before discounts (an order can mix kinds)."""
    totals = defaultdict(int)
    for item in OrderItem.objects.filter(order__in=orders).select_related("content_type"):
        model = item.content_type.model_class()
        label = model._meta.verbose_name_plural if model else item.content_type.model
        totals[str(label)] += item.line_total
    return sorted(totals.items(), key=lambda row: -row[1])
