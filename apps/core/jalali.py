"""Jalali (Shamsi) calendar helpers.

Datetimes are stored in UTC; these functions convert to Tehran time before
formatting, so callers can pass model fields directly.
"""

import datetime as dt

import jdatetime
from django.utils import timezone

from .text import to_en_digits, to_fa_digits

MONTHS = (
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
)
# jdatetime weekday(): Saturday == 0
WEEKDAYS = ("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه")


def to_jalali(value: dt.date | dt.datetime) -> jdatetime.date | jdatetime.datetime:
    """Gregorian -> Jalali. Aware datetimes are first converted to local (Tehran) time."""
    if isinstance(value, dt.datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return jdatetime.datetime.fromgregorian(datetime=value)
    return jdatetime.date.fromgregorian(date=value)


def format_date(value: dt.date | dt.datetime, *, weekday: bool = False) -> str:
    """-> '۳ آبان ۱۴۰۵' (or 'شنبه ۳ آبان ۱۴۰۵')."""
    j = to_jalali(value)
    text = f"{j.day} {MONTHS[j.month - 1]} {j.year}"
    if weekday:
        text = f"{WEEKDAYS[j.weekday()]} {text}"
    return to_fa_digits(text)


def format_datetime(value: dt.datetime) -> str:
    """-> '۳ آبان ۱۴۰۵، ساعت ۱۴:۳۰'."""
    j = to_jalali(value)
    return to_fa_digits(f"{j.day} {MONTHS[j.month - 1]} {j.year}، ساعت {j.hour:02d}:{j.minute:02d}")


def parse_date(text: str) -> dt.date:
    """'۱۴۰۵/۰۸/۰۳' or '1405-8-3' -> Gregorian date. Raises ValueError if invalid."""
    parts = to_en_digits(text.strip()).replace("-", "/").split("/")
    if len(parts) != 3:
        raise ValueError(f"invalid Jalali date: {text!r}")
    year, month, day = (int(p) for p in parts)
    return jdatetime.date(year, month, day).togregorian()
