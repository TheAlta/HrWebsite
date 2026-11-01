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
MIN_YEAR, MAX_YEAR = 1300, 1500


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


def format_time(value: dt.datetime) -> str:
    """-> '۱۴:۳۰' in Tehran time."""
    local = timezone.localtime(value)
    return to_fa_digits(f"{local.hour:02d}:{local.minute:02d}")


def parse_date(text: str) -> dt.date:
    """'۱۴۰۵/۰۸/۰۳' or '1405-8-3' -> Gregorian date. Raises ValueError if invalid."""
    parts = to_en_digits(text.strip()).replace("-", "/").split("/")
    if len(parts) != 3:
        raise ValueError(f"invalid Jalali date: {text!r}")
    year, month, day = (int(p) for p in parts)
    return jdatetime.date(year, month, day).togregorian()


def parse_datetime(text: str) -> dt.datetime:
    """'۱۴۰۵/۰۸/۲۰ ۱۸:۳۰' -> naive Gregorian datetime in Tehran time. Raises ValueError.

    The time part is optional and defaults to midnight. A year outside the Jalali
    range is refused, so a Gregorian date can never be read as a Jalali one.
    """
    date_text, _, time_text = to_en_digits(text.strip()).partition(" ")
    date = parse_date(date_text)
    if not MIN_YEAR <= to_jalali(date).year <= MAX_YEAR:
        raise ValueError(f"year out of Jalali range: {text!r}")
    hour, minute = (int(p) for p in (time_text.strip() or "0:0").split(":"))
    return dt.datetime.combine(date, dt.time(hour, minute))


def format_input(value: dt.datetime) -> str:
    """The form of a date that `parse_datetime` reads back: '۱۴۰۵/۰۸/۲۰ ۱۸:۳۰'."""
    j = to_jalali(value)
    return to_fa_digits(f"{j.year}/{j.month:02d}/{j.day:02d} {j.hour:02d}:{j.minute:02d}")


def month_days(year: int, month: int) -> list[dt.date]:
    """Every day of a Jalali month, as Gregorian dates."""
    first = jdatetime.date(year, month, 1).togregorian()
    following = jdatetime.date(year + (month == 12), month % 12 + 1, 1).togregorian()
    return [first + dt.timedelta(days=i) for i in range((following - first).days)]


def month_weeks(year: int, month: int) -> list[list[dt.date | None]]:
    """A Jalali month as calendar rows, Saturday first. Empty cells are None."""
    days = month_days(year, month)
    cells: list[dt.date | None] = [None] * to_jalali(days[0]).weekday() + days
    cells += [None] * (-len(cells) % 7)
    return [cells[i : i + 7] for i in range(0, len(cells), 7)]
