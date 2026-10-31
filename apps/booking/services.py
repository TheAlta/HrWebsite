"""Booking rules (BOOK-1..5, spec section 8.1).

Double booking is prevented by the database (`booking_no_overlap`); the slot
list here is only what the customer sees. Every write re-checks the rules, so
a crafted request cannot book a time that was never offered.
"""

import datetime as dt
from dataclasses import dataclass
from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.content.alerts import email_owner
from apps.core import jalali
from apps.notifications.services import send_sms
from apps.orders import services as orders
from apps.orders.services import OrderLine

from .models import Availability, Booking, SessionType, TimeOff

BOOKING_DAYS = 14
HOLD_MINUTES = 15
MIN_NOTICE = timedelta(hours=2)
MAX_ACTIVE_HOLDS = 2  # one account cannot block the calendar with unpaid holds
CHANGE_DEADLINE = timedelta(hours=24)  # latest customer cancel or reschedule (BOOK-4)
CALENDAR_LOCK_ID = 7_140_501  # any fixed number unique to this lock
SLOT_TAKEN = "این زمان همین الان رزرو شد. لطفاً زمان دیگری انتخاب کنید."


class BookingError(Exception):
    """A user-facing reason the action was refused (message is Persian)."""


@dataclass
class DaySlots:
    date: dt.date
    slots: list[dt.datetime]


def _persian_weekday(date: dt.date) -> int:
    # Python: Monday=0. Availability: Saturday=0.
    return (date.weekday() + 2) % 7


def _overlaps(start, end, ranges) -> bool:
    return any(start < range_end and end > range_start for range_start, range_end in ranges)


def free_slots(
    session_type: SessionType, *, now=None, days=BOOKING_DAYS, ignore: Booking | None = None
) -> list[DaySlots]:
    """Open start times for the next `days` days, in Tehran time (spec section 8.1, step 1).

    `ignore` leaves one booking out of the busy times, for rescheduling it.
    """
    now = now or timezone.now()
    today = timezone.localtime(now).date()
    horizon = now + timedelta(days=days + 1)
    earliest = now + MIN_NOTICE
    length = timedelta(minutes=session_type.duration_min)
    buffer = timedelta(minutes=session_type.buffer_min)

    busy_rows = Booking.objects.filter(
        status__in=Booking.ACTIVE_STATUSES, start_at__lt=horizon, blocked_until__gt=now
    ).exclude(status=Booking.Status.HELD, hold_expires_at__lte=now)
    if ignore is not None:
        busy_rows = busy_rows.exclude(pk=ignore.pk)
    busy = list(busy_rows.values_list("start_at", "blocked_until"))
    busy += list(TimeOff.objects.filter(start__lt=horizon, end__gt=now).values_list("start", "end"))

    working_hours: dict[int, list[Availability]] = {}
    for row in Availability.objects.all():
        working_hours.setdefault(row.weekday, []).append(row)

    days_out = []
    for offset in range(days):
        date = today + timedelta(days=offset)
        slots = []
        for window in working_hours.get(_persian_weekday(date), []):
            start = timezone.make_aware(dt.datetime.combine(date, window.start_time))
            window_end = timezone.make_aware(dt.datetime.combine(date, window.end_time))
            while start + length <= window_end:
                if start >= earliest and not _overlaps(start, start + length + buffer, busy):
                    slots.append(start)
                start += length + buffer
        if slots:
            days_out.append(DaySlots(date=date, slots=sorted(slots)))
    return days_out


def is_free(session_type, start_at, *, ignore=None) -> bool:
    local = timezone.localtime(start_at).date()
    for day in free_slots(session_type, ignore=ignore):
        if day.date == local:
            return start_at in day.slots
    return False


def _times(session_type, start_at):
    end_at = start_at + timedelta(minutes=session_type.duration_min)
    return end_at, end_at + timedelta(minutes=session_type.buffer_min)


def _lock_calendar():
    """Run calendar writes one at a time, until the surrounding transaction ends.

    Two simultaneous inserts of overlapping rows can deadlock inside PostgreSQL's
    exclusion check, and one customer would get a server error instead of a clear
    message (REPORT #037). There is one consultant and one calendar, so this
    short lock costs nothing; `booking_no_overlap` stays as the last line of defence.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [CALENDAR_LOCK_ID])


def hold_slot(user, session_type: SessionType, start_at) -> Booking:
    """Lock a slot for 15 minutes and create its order (spec section 8.1, step 3)."""
    if not session_type.is_active:
        raise BookingError("این نوع جلسه فعال نیست.")
    release_expired()
    end_at, blocked_until = _times(session_type, start_at)
    try:
        with transaction.atomic():
            _lock_calendar()
            own_holds = Booking.objects.filter(
                user=user, status=Booking.Status.HELD, hold_expires_at__gt=timezone.now()
            )
            # Back from the bank and paying again: the customer's own hold is still valid
            existing = own_holds.filter(session_type=session_type, start_at=start_at).first()
            if existing:
                return existing
            if own_holds.count() >= MAX_ACTIVE_HOLDS:
                raise BookingError(
                    "شما رزرو پرداخت‌نشده دارید. آن را تکمیل کنید یا چند دقیقه صبر کنید."
                )
            if not is_free(session_type, start_at):
                raise BookingError(SLOT_TAKEN)

            booking = Booking.objects.create(
                user=user,
                session_type=session_type,
                start_at=start_at,
                end_at=end_at,
                blocked_until=blocked_until,
                hold_expires_at=timezone.now() + timedelta(minutes=HOLD_MINUTES),
            )
            line = OrderLine(item=booking, title=_title(booking), unit_price=session_type.price)
            booking.order = orders.create_order(user, [line])
            booking.save(update_fields=["order"])
    except IntegrityError as exc:
        # Backstop: the calendar lock should make this unreachable
        raise BookingError(SLOT_TAKEN) from exc

    if booking.order.total == 0:
        # Free session: there is nothing to pay, so it goes straight to delivery
        with transaction.atomic():
            orders.mark_paid(booking.order)
        orders.fulfil(booking.order)
        booking.refresh_from_db()
    return booking


def _title(booking: Booking) -> str:
    when = jalali.format_datetime(booking.start_at)
    return f"{booking.session_type.title} — {when}"


def release_expired(now=None) -> int:
    """Free slots whose 15-minute hold ran out unpaid (spec section 8.1, step 7)."""
    now = now or timezone.now()
    expired = Booking.objects.filter(status=Booking.Status.HELD, hold_expires_at__lte=now)
    count = 0
    for booking in expired.select_related("order"):
        updated = Booking.objects.filter(pk=booking.pk, status=Booking.Status.HELD).update(
            status=Booking.Status.EXPIRED
        )
        if updated and booking.order:
            orders.cancel_unpaid(booking.order)
        count += updated
    return count


def confirm_bookings_for_order(order) -> None:
    """A paid order confirms its bookings (receiver of `order_paid`)."""
    for booking in Booking.objects.select_for_update().filter(order=order):
        if booking.status == Booking.Status.CONFIRMED:
            continue
        reclaimable = booking.status == Booking.Status.EXPIRED and _try_reclaim(booking)
        if booking.status != Booking.Status.HELD and not reclaimable:
            # Paid after the hold ran out and the slot is gone, or the owner cancelled it
            _report_lost_slot(booking)
            continue
        booking.status = Booking.Status.CONFIRMED
        booking.hold_expires_at = None
        booking.meeting_link = booking.meeting_link or booking.session_type.meeting_link
        booking.save(update_fields=["status", "hold_expires_at", "meeting_link"])
        _notify_confirmed(booking)


def _try_reclaim(booking: Booking) -> bool:
    try:
        with transaction.atomic():
            _lock_calendar()
            Booking.objects.filter(pk=booking.pk).update(status=Booking.Status.CONFIRMED)
    except IntegrityError:
        return False
    return True


def _notify_confirmed(booking: Booking):
    send_sms(
        booking.user.mobile,
        "booking_confirmed",
        {"token": booking.order.number if booking.order else "-", "token10": _when(booking)},
    )
    email_owner(
        f"رزرو جدید: {booking.session_type.title}",
        f"{booking.user} — {_when(booking)}",
    )


def _report_lost_slot(booking: Booking):
    send_sms(booking.user.mobile, "booking_problem", {"token10": _when(booking)})
    email_owner(
        "پرداخت بعد از انقضای رزرو",
        f"سفارش {booking.order.number}: {booking.user} بعد از پایان قفل پرداخت کرد و زمان "
        f"{_when(booking)} را شخص دیگری گرفته است. زمان جدید هماهنگ یا مبلغ برگردانده شود.",
    )


def _when(booking: Booking) -> str:
    return jalali.format_datetime(booking.start_at)


def can_change(booking: Booking, now=None) -> bool:
    now = now or timezone.now()
    return booking.status == Booking.Status.CONFIRMED and booking.start_at - now >= CHANGE_DEADLINE


def cancel(booking: Booking, *, by_owner=False) -> Booking:
    """Cancel a session (BOOK-4). Customers: up to 24 hours before; the owner: any time."""
    if not by_owner and not can_change(booking):
        raise BookingError("لغو جلسه فقط تا ۲۴ ساعت قبل از شروع ممکن است.")
    was_paid = bool(
        booking.order and booking.order.total and booking.status == Booking.Status.CONFIRMED
    )
    if booking.status == Booking.Status.HELD and booking.order:
        orders.cancel_unpaid(booking.order)
    booking.status = Booking.Status.CANCELLED
    booking.save(update_fields=["status"])
    send_sms(booking.user.mobile, "booking_cancelled", {"token10": _when(booking)})
    if was_paid:
        # Automatic refunds arrive with PAY-4 (sprint 5)
        email_owner(
            "لغو جلسه پرداخت‌شده",
            f"سفارش {booking.order.number}: جلسه {_when(booking)} لغو شد. "
            "بازگشت وجه به‌صورت دستی انجام شود.",
        )
    return booking


def reschedule(booking: Booking, new_start) -> Booking:
    """Move a confirmed session to another free time (BOOK-4)."""
    if not can_change(booking):
        raise BookingError("جابه‌جایی جلسه فقط تا ۲۴ ساعت قبل از شروع ممکن است.")

    end_at, blocked_until = _times(booking.session_type, new_start)
    try:
        with transaction.atomic():
            _lock_calendar()
            if not is_free(booking.session_type, new_start, ignore=booking):
                raise BookingError(SLOT_TAKEN)
            booking.start_at, booking.end_at = new_start, end_at
            booking.blocked_until = blocked_until
            # Reminders must fire again for the new time
            booking.reminded_24h_at = booking.reminded_1h_at = None
            booking.save(
                update_fields=[
                    "start_at",
                    "end_at",
                    "blocked_until",
                    "reminded_24h_at",
                    "reminded_1h_at",
                ]
            )
    except IntegrityError as exc:
        booking.refresh_from_db()
        raise BookingError(SLOT_TAKEN) from exc
    send_sms(
        booking.user.mobile,
        "booking_confirmed",
        {"token": booking.order.number if booking.order else "-", "token10": _when(booking)},
    )
    return booking


def send_reminders(now=None) -> int:
    """Every 5 minutes: SMS 24 hours and 1 hour before a session (BOOK-5)."""
    now = now or timezone.now()
    day, hour = timedelta(hours=24), timedelta(hours=1)
    sent = 0
    for field, lead in (("reminded_24h_at", day), ("reminded_1h_at", hour)):
        due = Booking.objects.filter(
            status=Booking.Status.CONFIRMED,
            start_at__gt=now,
            start_at__lte=now + lead,
            **{f"{field}__isnull": True},
        ).select_related("user", "session_type")
        for booking in due:
            # A claimed row can never be sent twice, even if two workers overlap
            claimed = Booking.objects.filter(pk=booking.pk, **{f"{field}__isnull": True}).update(
                **{field: now}
            )
            if not claimed:
                continue
            # The day-before message is pointless for a session booked less than a day
            # ahead, or when only the one-hour reminder is left
            booked_late = booking.start_at - booking.created_at < day
            if field == "reminded_24h_at" and (booked_late or booking.start_at - now <= hour):
                continue
            send_sms(
                booking.user.mobile,
                "booking_reminder",
                {"token10": _when(booking), "token20": booking.meeting_link or "-"},
            )
            sent += 1
    return sent


def housekeeping() -> None:
    """Every minute: release expired holds and close finished sessions."""
    release_expired()
    Booking.objects.filter(status=Booking.Status.CONFIRMED, end_at__lt=timezone.now()).update(
        status=Booking.Status.DONE
    )
