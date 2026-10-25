import datetime as dt

import pytest

from apps.core.jalali import format_date, format_datetime, parse_date, to_jalali


def test_date_to_jalali():
    j = to_jalali(dt.date(2026, 10, 25))
    assert (j.year, j.month, j.day) == (1405, 8, 3)


def test_format_date():
    assert format_date(dt.date(2026, 10, 25)) == "۳ آبان ۱۴۰۵"
    assert format_date(dt.date(2026, 10, 25), weekday=True) == "یکشنبه ۳ آبان ۱۴۰۵"


def test_utc_datetime_is_shown_in_tehran_time():
    # 22:00 UTC is already the next day in Tehran (UTC+3:30)
    value = dt.datetime(2026, 10, 24, 22, 0, tzinfo=dt.UTC)
    assert format_datetime(value) == "۳ آبان ۱۴۰۵، ساعت ۰۱:۳۰"


def test_nowruz_boundary():
    assert format_date(dt.date(2026, 3, 21)) == "۱ فروردین ۱۴۰۵"


@pytest.mark.parametrize("text", ["۱۴۰۵/۰۸/۰۳", "1405-8-3", " 1405/08/03 "])
def test_parse_date(text):
    assert parse_date(text) == dt.date(2026, 10, 25)


@pytest.mark.parametrize("text", ["1405/13/01", "1405/08", "hello"])
def test_parse_invalid_date(text):
    with pytest.raises(ValueError):
        parse_date(text)
