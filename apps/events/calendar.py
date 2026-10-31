"""What the /events page shows: a list, or one Jalali month (EVT-2)."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from django.utils import timezone

from apps.core import jalali

from .models import EventPage, EventSession

PAST_EVENTS_SHOWN = 6


@dataclass
class DayCell:
    date: date
    is_today: bool
    events: list[EventPage] = field(default_factory=list)


def _month_from(request) -> tuple[int, int]:
    today = jalali.to_jalali(timezone.localdate())
    try:
        year = int(request.GET.get("y", today.year))
        month = int(request.GET.get("m", today.month))
    except ValueError:
        return today.year, today.month
    if not (jalali.MIN_YEAR <= year <= jalali.MAX_YEAR and 1 <= month <= 12):
        return today.year, today.month
    return year, month


def _shift(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _local_range(days: list[date]) -> tuple[datetime, datetime]:
    start = timezone.make_aware(datetime.combine(days[0], datetime.min.time()))
    end = timezone.make_aware(datetime.combine(days[-1], datetime.max.time()))
    return start, end


def month_view(events, request) -> dict:
    year, month = _month_from(request)
    start, end = _local_range(jalali.month_days(year, month))

    by_day = defaultdict(list)
    for event in events.filter(start_at__range=(start, end)):
        by_day[timezone.localdate(event.start_at)].append(event)
    sessions = EventSession.objects.filter(
        start_at__range=(start, end), event__in=events
    ).select_related("event")
    for session in sessions:
        day = by_day[timezone.localdate(session.start_at)]
        if not any(event.pk == session.event_id for event in day):
            day.append(session.event)

    today = timezone.localdate()
    weeks = [
        [
            day and DayCell(date=day, is_today=day == today, events=by_day.get(day, []))
            for day in week
        ]
        for week in jalali.month_weeks(year, month)
    ]
    month_events = sorted(
        {event.pk: event for day in by_day.values() for event in day}.values(),
        key=lambda event: event.start_at,
    )
    previous, following = _shift(year, month, -1), _shift(year, month, 1)
    return {
        "weeks": weeks,
        "weekdays": jalali.WEEKDAYS,
        "month_label": f"{jalali.MONTHS[month - 1]} {year}",
        "month_events": month_events,
        "previous_month": {"y": previous[0], "m": previous[1]},
        "next_month": {"y": following[0], "m": following[1]},
    }


def index_context(page, request) -> dict:
    events = (
        EventPage.objects.child_of(page)
        .live()
        .exclude(kind=EventPage.Kind.TALK)
        .select_related("cover_image")
    )
    if request.GET.get("view") == "month":
        return {"view": "month", **month_view(events, request)}
    now = timezone.now()
    return {
        "view": "list",
        "upcoming": events.filter(end_at__gte=now).order_by("start_at"),
        "past": events.filter(end_at__lt=now).order_by("-start_at")[:PAST_EVENTS_SHOWN],
    }
