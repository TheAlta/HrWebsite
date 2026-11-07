"""Panel columns that show dates in Shamsi and amounts in Tomans (spec section 4).

    paid_display = jalali_column("paid_at", "زمان پرداخت")

A model field shown as it is would print a Gregorian date or a bare Rial number.
"""

from django.contrib import admin

from . import jalali
from .money import format_toman

EMPTY = "—"


def jalali_column(field: str, label: str):
    @admin.display(description=label, ordering=field)
    def column(obj):
        value = getattr(obj, field)
        return jalali.format_datetime(value) if value else EMPTY

    return column


def toman_column(field: str, label: str):
    @admin.display(description=label, ordering=field)
    def column(obj):
        return format_toman(getattr(obj, field) or 0)

    return column


def optional_column(field: str, label: str):
    @admin.display(description=label)
    def column(obj):
        return getattr(obj, field) or EMPTY

    return column
