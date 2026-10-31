import datetime as dt
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.booking import services
from apps.booking.models import Availability, Booking, TimeOff

pytestmark = pytest.mark.django_db

TEHRAN = dt.timezone(dt.timedelta(hours=3, minutes=30))
# A Saturday morning in Tehran
NOW = dt.datetime(2026, 11, 7, 6, 0, tzinfo=TEHRAN)


def tehran(*args):
    return dt.datetime(*args, tzinfo=TEHRAN)


def hours(weekday, start=(9, 0), end=(13, 0)):
    return Availability.objects.create(
        weekday=weekday, start_time=dt.time(*start), end_time=dt.time(*end)
    )


def times(day):
    return [timezone.localtime(s).strftime("%H:%M") for s in day.slots]


def test_slots_follow_duration_and_buffer_in_tehran_time(session_type):
    hours(Availability.Weekday.SATURDAY)
    day = services.free_slots(session_type, now=NOW)[0]
    assert day.date == dt.date(2026, 11, 7)
    # 60 minutes + 15 buffer; 12:45 would end after 13:00
    assert times(day) == ["09:00", "10:15", "11:30"]


def test_weekday_numbering_starts_on_saturday(session_type):
    hours(Availability.Weekday.FRIDAY)
    days = services.free_slots(session_type, now=NOW)
    assert days and all(d.date.weekday() == 4 for d in days)  # Python: Friday is 4


def test_lunch_break_is_two_windows(session_type):
    hours(Availability.Weekday.SATURDAY, (9, 0), (10, 0))
    hours(Availability.Weekday.SATURDAY, (14, 0), (15, 0))
    assert times(services.free_slots(session_type, now=NOW)[0]) == ["09:00", "14:00"]


def test_minimum_notice_hides_near_times(session_type):
    hours(Availability.Weekday.SATURDAY)
    now = tehran(2026, 11, 7, 8, 30)  # 09:00 and 10:15 are under two hours away
    assert times(services.free_slots(session_type, now=now)[0]) == ["11:30"]


def test_booking_window_is_fourteen_days(session_type):
    for weekday in Availability.Weekday.values:
        hours(weekday)
    days = services.free_slots(session_type, now=NOW)
    assert len(days) == services.BOOKING_DAYS
    assert days[-1].date == dt.date(2026, 11, 20)


def test_time_off_removes_overlapping_slots(session_type):
    hours(Availability.Weekday.SATURDAY)
    TimeOff.objects.create(start=tehran(2026, 11, 7, 10, 0), end=tehran(2026, 11, 7, 11, 0))
    assert times(services.free_slots(session_type, now=NOW)[0]) == ["11:30"]


def make_booking(session_type, customer, start, **kwargs):
    end = start + timedelta(minutes=session_type.duration_min)
    defaults = {"status": Booking.Status.CONFIRMED}
    return Booking.objects.create(
        user=customer,
        session_type=session_type,
        start_at=start,
        end_at=end,
        blocked_until=end + timedelta(minutes=session_type.buffer_min),
        **{**defaults, **kwargs},
    )


def test_bookings_and_their_buffer_are_busy(session_type, customer):
    hours(Availability.Weekday.SATURDAY)
    make_booking(session_type, customer, tehran(2026, 11, 7, 10, 15))
    assert times(services.free_slots(session_type, now=NOW)[0]) == ["09:00", "11:30"]


def test_expired_hold_does_not_block(session_type, customer):
    hours(Availability.Weekday.SATURDAY)
    make_booking(
        session_type,
        customer,
        tehran(2026, 11, 7, 10, 15),
        status=Booking.Status.HELD,
        hold_expires_at=NOW - timedelta(minutes=1),
    )
    assert "10:15" in times(services.free_slots(session_type, now=NOW)[0])


def test_cancelled_booking_frees_the_time(session_type, customer):
    hours(Availability.Weekday.SATURDAY)
    make_booking(
        session_type, customer, tehran(2026, 11, 7, 10, 15), status=Booking.Status.CANCELLED
    )
    assert "10:15" in times(services.free_slots(session_type, now=NOW)[0])
