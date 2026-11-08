"""Busy times from the owner's own calendars (BOOK-6, REPORT #051).

Each feed is a calendar's secret iCal address, from Google, Outlook or Apple.
Only start and end leave this module: titles and descriptions are never stored.
The address is a secret, so it never appears in a log or an error message.
"""

import datetime as dt

import httpx
import recurring_ical_events
from django.conf import settings
from django.utils import timezone
from icalendar import Calendar

MAX_FEED_BYTES = 5 * 1024 * 1024
MAX_RANGES = 2000  # a runaway recurrence must not fill the table
TIMEOUT = 20

Range = tuple[dt.datetime, dt.datetime]


class FeedError(Exception):
    """Why a feed could not be read, never with its address."""


def feed_urls() -> list[str]:
    return [url for url in settings.BUSY_CALENDAR_URLS if url]


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, follow_redirects=True)


def fetch(url: str) -> bytes:
    try:
        with _client() as client, client.stream("GET", url) as response:
            if response.status_code != 200:
                raise FeedError(f"HTTP {response.status_code}")
            body = bytearray()
            for chunk in response.iter_bytes():
                body += chunk
                if len(body) > MAX_FEED_BYTES:
                    raise FeedError("larger than 5 MB")
            return bytes(body)
    except httpx.HTTPError as exc:
        # `from None`: the original exception text can carry the address
        raise FeedError(type(exc).__name__) from None


def busy_ranges(data: bytes, start: dt.datetime, end: dt.datetime) -> list[Range]:
    """Busy times between start and end, with repeating events expanded."""
    try:
        events = recurring_ical_events.of(Calendar.from_ical(data)).between(start, end)
    except Exception as exc:  # any parser failure means the same thing: not a calendar
        raise FeedError(f"not a calendar ({type(exc).__name__})") from None
    ranges = []
    for event in events:
        if str(event.get("TRANSP", "")).upper() == "TRANSPARENT":
            continue  # marked "free" in the calendar
        if str(event.get("STATUS", "")).upper() == "CANCELLED":
            continue
        begin = _aware(event.decoded("DTSTART"))
        finish = _aware(event.decoded("DTEND")) if "DTEND" in event else None
        if finish is None and not isinstance(event.decoded("DTSTART"), dt.datetime):
            finish = begin + dt.timedelta(days=1)  # an all-day event with no end
        if finish is None or finish <= begin:
            continue
        ranges.append((begin, finish))
        if len(ranges) > MAX_RANGES:
            raise FeedError(f"more than {MAX_RANGES} busy times")
    return sorted(ranges)


def _aware(value) -> dt.datetime:
    """All-day dates and times without a zone are read as Tehran time."""
    if not isinstance(value, dt.datetime):
        value = dt.datetime.combine(value, dt.time.min)
    if timezone.is_naive(value):
        value = timezone.make_aware(value)
    return value
