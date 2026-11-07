"""Busy times from the owner's calendars (BOOK-6)."""

import datetime as dt
from datetime import timedelta

import httpx
import pytest
from django.core import mail
from django.core.management import CommandError, call_command
from django.utils import timezone

from apps.booking import calendars, services
from apps.booking.models import CalendarBusy, CalendarSync
from apps.content.models import SiteSettings

pytestmark = pytest.mark.django_db

SECRET = "https://calendar.example/ical/owner%40gmail.com/private-0123456789abcdef/basic.ics"
TEHRAN = timezone.get_default_timezone()


def ics(*events: str) -> bytes:
    body = "\r\n".join(events)
    return (
        f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//EN\r\n{body}\r\nEND:VCALENDAR\r\n"
    ).encode()


def event(start: str, end: str = "", *extra: str, uid="1") -> str:
    lines = ["BEGIN:VEVENT", f"UID:{uid}", "SUMMARY:دندان‌پزشکی", start]
    if end:
        lines.append(end)
    return "\r\n".join([*lines, *extra, "END:VEVENT"])


def local(*args) -> dt.datetime:
    return timezone.make_aware(dt.datetime(*args), TEHRAN)


WINDOW = (local(2026, 11, 1), local(2026, 11, 20))


def ranges(data):
    return calendars.busy_ranges(data, *WINDOW)


@pytest.fixture
def feed(settings, monkeypatch):
    """Serve `feed.body` at the secret address through a fake network."""

    class Feed:
        body = ics()
        status = 200
        error = None

    def handler(request):
        if Feed.error:
            raise Feed.error
        return httpx.Response(Feed.status, content=Feed.body)

    settings.BUSY_CALENDAR_URLS = [SECRET]
    monkeypatch.setattr(
        calendars, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    return Feed


# --- reading a calendar ---------------------------------------------------------------------


def test_a_timed_event_is_busy():
    data = ics(event("DTSTART:20261110T063000Z", "DTEND:20261110T073000Z"))
    assert ranges(data) == [(local(2026, 11, 10, 10, 0), local(2026, 11, 10, 11, 0))]


def test_an_event_marked_free_is_ignored():
    data = ics(event("DTSTART:20261110T063000Z", "DTEND:20261110T073000Z", "TRANSP:TRANSPARENT"))
    assert ranges(data) == []


def test_a_cancelled_event_is_ignored():
    data = ics(event("DTSTART:20261110T063000Z", "DTEND:20261110T073000Z", "STATUS:CANCELLED"))
    assert ranges(data) == []


def test_a_busy_all_day_event_blocks_the_tehran_day():
    data = ics(event("DTSTART;VALUE=DATE:20261112", "DTEND;VALUE=DATE:20261113"))
    assert ranges(data) == [(local(2026, 11, 12), local(2026, 11, 13))]


def test_an_all_day_event_without_an_end_lasts_one_day():
    data = ics(event("DTSTART;VALUE=DATE:20261112"))
    assert ranges(data) == [(local(2026, 11, 12), local(2026, 11, 13))]


def test_a_time_without_a_zone_is_tehran_time():
    data = ics(event("DTSTART:20261110T100000", "DTEND:20261110T110000"))
    assert ranges(data) == [(local(2026, 11, 10, 10, 0), local(2026, 11, 10, 11, 0))]


def test_a_duration_gives_the_end():
    data = ics(event("DTSTART:20261110T063000Z", "", "DURATION:PT45M"))
    assert ranges(data) == [(local(2026, 11, 10, 10, 0), local(2026, 11, 10, 10, 45))]


def test_a_weekly_event_repeats_inside_the_window():
    data = ics(
        event(
            "DTSTART;TZID=Asia/Tehran:20261003T170000",
            "DTEND;TZID=Asia/Tehran:20261003T183000",
            "RRULE:FREQ=WEEKLY",
        )
    )
    starts = [start for start, _ in ranges(data)]
    assert starts == [
        local(2026, 11, 7, 17, 0),
        local(2026, 11, 14, 17, 0),
    ]


def test_events_outside_the_window_are_left_out():
    data = ics(event("DTSTART:20261225T063000Z", "DTEND:20261225T073000Z"))
    assert ranges(data) == []


def test_something_that_is_not_a_calendar_is_an_error():
    with pytest.raises(calendars.FeedError, match="not a calendar"):
        ranges(b"<html>login</html>")


# --- fetching -------------------------------------------------------------------------------


def test_fetch_returns_the_feed(feed):
    feed.body = b"BEGIN:VCALENDAR"
    assert calendars.fetch(SECRET) == b"BEGIN:VCALENDAR"


def test_an_http_error_never_shows_the_address(feed):
    feed.status = 404
    with pytest.raises(calendars.FeedError) as caught:
        calendars.fetch(SECRET)
    assert str(caught.value) == "HTTP 404"
    assert caught.value.__cause__ is None


def test_a_network_error_never_shows_the_address(feed):
    feed.error = httpx.ConnectError(f"cannot reach {SECRET}")
    with pytest.raises(calendars.FeedError) as caught:
        calendars.fetch(SECRET)
    assert SECRET not in str(caught.value)
    assert caught.value.__suppress_context__


def test_a_huge_feed_is_refused(feed, monkeypatch):
    monkeypatch.setattr(calendars, "MAX_FEED_BYTES", 10)
    feed.body = b"x" * 11
    with pytest.raises(calendars.FeedError, match="larger"):
        calendars.fetch(SECRET)


# --- syncing --------------------------------------------------------------------------------


def soon(hours=30):
    start = timezone.now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=hours)
    return start, start + timedelta(hours=1)


def feed_with(start, end):
    fmt = "%Y%m%dT%H%M%SZ"
    return ics(
        event(f"DTSTART:{start.astimezone(dt.UTC):{fmt}}", f"DTEND:{end.astimezone(dt.UTC):{fmt}}")
    )


def test_off_without_addresses(settings):
    settings.BUSY_CALENDAR_URLS = []
    assert services.sync_calendars() is None
    assert not CalendarSync.objects.exists()


def test_turning_it_off_drops_the_copied_times(settings):
    CalendarBusy.objects.create(start=timezone.now(), end=timezone.now() + timedelta(hours=1))
    settings.BUSY_CALENDAR_URLS = []
    services.sync_calendars()
    assert not CalendarBusy.objects.exists()


def test_sync_replaces_the_busy_times(feed):
    CalendarBusy.objects.create(start=timezone.now(), end=timezone.now() + timedelta(hours=1))
    start, end = soon()
    feed.body = feed_with(start, end)
    assert services.sync_calendars() == 1
    assert list(CalendarBusy.objects.values_list("start", "end")) == [(start, end)]
    state = CalendarSync.objects.get()
    assert state.failures == 0
    assert state.last_success_at is not None


def test_only_times_are_stored():
    field_names = {field.name for field in CalendarBusy._meta.get_fields()}
    assert field_names == {"id", "start", "end"}


def test_a_failed_read_keeps_the_last_good_times(feed):
    start, end = soon()
    feed.body = feed_with(start, end)
    services.sync_calendars()
    feed.status = 500
    assert services.sync_calendars() is None
    assert CalendarBusy.objects.count() == 1
    state = CalendarSync.objects.get()
    assert state.failures == 1
    assert state.last_error == "calendar 1: HTTP 500"


def test_the_owner_is_emailed_once_when_reads_keep_failing(feed, demo_site):
    site_settings = SiteSettings.for_default_site()
    site_settings.notify_email = "owner@example.com"
    site_settings.save()
    feed.status = 503
    for _ in range(services.CALENDAR_ALERT_AFTER + 2):
        services.sync_calendars()
    alerts = [m for m in mail.outbox if "تقویم" in m.subject]
    assert len(alerts) == 1
    assert SECRET not in alerts[0].body


def test_a_good_read_resets_the_failure_count(feed):
    feed.status = 500
    services.sync_calendars()
    feed.status = 200
    services.sync_calendars()
    assert CalendarSync.objects.get().failures == 0


def test_one_broken_calendar_of_two_fails_the_read(feed, settings):
    settings.BUSY_CALENDAR_URLS = [SECRET, "https://calendar.example/second.ics"]
    feed.body = b"not a calendar"
    with pytest.raises(calendars.FeedError, match="calendar 1"):
        services.read_calendars()


# --- booking ---------------------------------------------------------------------------------


def test_a_busy_time_removes_the_slots_it_covers(session_type, every_day, feed):
    first = services.free_slots(session_type)[0].slots[0]
    feed.body = feed_with(first, first + timedelta(minutes=30))
    services.sync_calendars()
    slots = [slot for day in services.free_slots(session_type) for slot in day.slots]
    assert first not in slots


def test_a_busy_time_is_refused_at_hold(session_type, every_day, customer, feed):
    first = services.free_slots(session_type)[0].slots[0]
    feed.body = feed_with(first, first + timedelta(minutes=30))
    services.sync_calendars()
    with pytest.raises(services.BookingError):
        services.hold_slot(customer, session_type, first)


# --- the check command ----------------------------------------------------------------------


def test_check_reports_off(settings, capsys):
    settings.BUSY_CALENDAR_URLS = []
    call_command("check_calendar")
    assert "off" in capsys.readouterr().out


def test_check_reports_what_it_read_without_saving(feed, capsys):
    start, end = soon()
    feed.body = feed_with(start, end)
    call_command("check_calendar")
    out = capsys.readouterr().out
    assert "1 busy time(s)" in out
    assert not CalendarBusy.objects.exists()
    assert SECRET not in out


def test_check_fails_loudly(feed):
    feed.status = 403
    with pytest.raises(CommandError, match="HTTP 403"):
        call_command("check_calendar")
