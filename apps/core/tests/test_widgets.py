import datetime as dt

import pytest
from django import forms

from apps.core import jalali
from apps.core.widgets import JalaliDateTimeInput


class EventForm(forms.Form):
    start = forms.DateTimeField(widget=JalaliDateTimeInput)


def test_shamsi_input_becomes_a_gregorian_datetime():
    form = EventForm({"start": "۱۴۰۵/۰۸/۲۰ ۱۸:۳۰"})
    assert form.is_valid()
    value = form.cleaned_data["start"]
    assert (value.year, value.month, value.day) == (2026, 11, 11)
    assert (value.hour, value.minute) == (18, 30)


def test_english_digits_and_date_only():
    form = EventForm({"start": "1405/8/20"})
    assert form.is_valid()
    assert form.cleaned_data["start"].hour == 0


def test_stored_value_is_shown_in_shamsi():
    form = EventForm(initial={"start": dt.datetime(2026, 11, 11, 18, 30)})
    assert "۱۴۰۵/۰۸/۲۰ ۱۸:۳۰" in str(form["start"])


def test_form_shown_again_after_an_error_stays_shamsi():
    """A second submit must not read the converted date as a Shamsi one."""
    form = EventForm({"start": "1405/08/20 18:30"})
    assert "۱۴۰۵/۰۸/۲۰ ۱۸:۳۰" in str(form["start"])


@pytest.mark.parametrize("text", ["فردا", "1405/13/01", "1405/08/20 25:00"])
def test_bad_text_is_reported_not_guessed(text):
    assert not EventForm({"start": text}).is_valid()


def test_gregorian_year_is_never_read_as_shamsi():
    with pytest.raises(ValueError):
        jalali.parse_datetime("2026/11/11 18:30")


def test_format_and_parse_are_the_same_moment():
    moment = dt.datetime(2026, 3, 20, 23, 59)
    assert jalali.parse_datetime(jalali.format_input(moment)) == moment


def test_month_grid_starts_on_saturday():
    weeks = jalali.month_weeks(1405, 8)
    assert all(len(week) == 7 for week in weeks)
    first_row_days = [day for day in weeks[0] if day]
    assert jalali.to_jalali(first_row_days[0]).day == 1
    assert jalali.to_jalali(first_row_days[0]).weekday() == weeks[0].index(first_row_days[0])


@pytest.mark.parametrize(("year", "month", "days"), [(1405, 1, 31), (1405, 7, 30), (1403, 12, 30)])
def test_month_lengths(year, month, days):
    assert len(jalali.month_days(year, month)) == days
