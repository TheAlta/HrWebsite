"""Event registration (EVT-1..4, spec section 8.3).

Seats are never oversold: every change to who holds a seat happens with the
event row locked, and `taken_seats` counts confirmed customers plus holds that
have not run out. A paid registration holds its seat while the customer pays;
when a seat frees up, the oldest person on the waiting list is offered it.

Lock order: `orders.fulfil` holds the order row and then asks for the event, so
code that holds the event must not touch an existing order. Orders of ended
holds are cancelled after the event lock is released.
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.content.alerts import email_owner
from apps.core import jalali
from apps.notifications.services import send_sms
from apps.orders import services as orders
from apps.orders.services import OrderLine

from .models import EventPage, Registration

SEAT_HOLD = timedelta(minutes=15)
WAITLIST_HOLD = timedelta(hours=24)  # time to pay after a seat is offered
SMS_TITLE_WORDS = 8  # Kavenegar limits the spaces in token20


class RegistrationError(Exception):
    """A user-facing reason the action was refused (message is Persian)."""


def _lock_event(event_id: int) -> EventPage:
    """Serialise seat changes per event, until the surrounding transaction ends."""
    return EventPage.objects.select_for_update(of=("self",)).get(pk=event_id)


def taken_seats(event: EventPage, now=None) -> int:
    now = now or timezone.now()
    return event.registrations.filter(
        Q(status=Registration.Status.PAID)
        | Q(status=Registration.Status.PENDING, hold_expires_at__gt=now)
    ).count()


def seats_left(event: EventPage, now=None) -> int | None:
    """Free seats, or None when the event has no limit."""
    if event.capacity is None:
        return None
    return max(event.capacity - taken_seats(event, now), 0)


def _has_seat(event: EventPage, now) -> bool:
    return event.capacity is None or taken_seats(event, now) < event.capacity


def active_registration(user, event: EventPage) -> Registration | None:
    return event.registrations.filter(user=user, status__in=Registration.ACTIVE_STATUSES).first()


def register(user, event: EventPage) -> Registration:
    """Give the customer a seat, or a place on the waiting list (spec section 8.3)."""
    now = timezone.now()
    with transaction.atomic():
        event = _lock_event(event.pk)
        unpaid = _expire_holds(event, now)
        _fill_seats(event, now)
        registration = active_registration(user, event)  # back from the bank, or a repeated click
        if registration is None and event.registration_open:
            registration = _join(user, event, now)
    _cancel_orders(unpaid)
    if registration is None:
        raise RegistrationError("ثبت‌نام این رویداد بسته شده است.")
    return registration


def _join(user, event: EventPage, now) -> Registration:
    someone_waiting = event.registrations.filter(status=Registration.Status.WAITLIST).exists()
    if someone_waiting or not _has_seat(event, now):
        registration = Registration.objects.create(
            event=event, user=user, status=Registration.Status.WAITLIST
        )
        send_sms(user.mobile, "event_waitlisted", {"token20": _title(event)})
        return registration

    registration = Registration(event=event, user=user)
    if event.is_free:
        _confirm(registration)
    else:
        _hold_seat(registration, now + SEAT_HOLD)
    return registration


def _hold_seat(registration: Registration, until) -> None:
    """Reserve a seat until `until` and create the order to pay for it."""
    registration.status = Registration.Status.PENDING
    registration.hold_expires_at = until
    registration.save()
    event = registration.event
    line = OrderLine(item=registration, title=event.title, unit_price=event.price)
    registration.order = orders.create_order(registration.user, [line])
    registration.save(update_fields=["order"])


def _confirm(registration: Registration) -> None:
    registration.status = Registration.Status.PAID
    registration.hold_expires_at = None
    registration.save()
    event = registration.event
    send_sms(
        registration.user.mobile,
        "event_registered",
        {"token": event.join_link or "-", "token10": _when(event), "token20": _title(event)},
    )


def _expire_holds(event: EventPage, now) -> list:
    """End unpaid holds and return their orders, to cancel after the lock is released."""
    expired = list(
        event.registrations.filter(
            status=Registration.Status.PENDING, hold_expires_at__lte=now
        ).select_related("order")
    )
    for registration in expired:
        registration.status = Registration.Status.EXPIRED
        registration.save(update_fields=["status"])
    return [registration.order for registration in expired]


def _cancel_orders(unpaid: list) -> None:
    for order in unpaid:
        orders.cancel_unpaid(order)


def _fill_seats(event: EventPage, now) -> None:
    """Offer free seats to the waiting list, oldest first. Needs the event lock."""
    if event.start_at <= now:
        return
    waiting = (
        event.registrations.filter(status=Registration.Status.WAITLIST)
        .select_related("user")
        .order_by("created_at")
    )
    free = seats_left(event, now)
    for registration in waiting if free is None else waiting[:free]:
        registration.event = event
        if event.is_free:
            _confirm(registration)
            continue
        until = min(now + WAITLIST_HOLD, event.start_at)
        _hold_seat(registration, until)
        send_sms(
            registration.user.mobile,
            "event_seat_open",
            {"token10": jalali.format_datetime(until), "token20": _title(event)},
        )


def confirm_registrations_for_order(order) -> None:
    """A paid order confirms its registration (receiver of `order_paid`).

    A payment can arrive after the hold ran out. The customer keeps the place if a
    seat is still free; otherwise the owner is told, because money came in.
    """
    now = timezone.now()
    for row in Registration.objects.filter(order=order).only("pk", "event_id"):
        event = _lock_event(row.event_id)
        registration = Registration.objects.select_related("user").get(pk=row.pk)
        registration.event = event
        if registration.is_confirmed:
            continue
        hold_valid = (
            registration.status == Registration.Status.PENDING
            and registration.hold_expires_at > now
        )
        if hold_valid or _can_reclaim(registration, event, now):
            _confirm(registration)
        else:
            _report_lost_seat(registration)


def _can_reclaim(registration: Registration, event: EventPage, now) -> bool:
    late = registration.status in (Registration.Status.PENDING, Registration.Status.EXPIRED)
    other_active = (
        event.registrations.filter(user=registration.user, status__in=Registration.ACTIVE_STATUSES)
        .exclude(pk=registration.pk)
        .exists()
    )
    return late and not other_active and _has_seat(event, now)


def _report_lost_seat(registration: Registration) -> None:
    event = registration.event
    send_sms(registration.user.mobile, "event_problem", {"token20": _title(event)})
    email_owner(
        "پرداخت بدون صندلی",
        f"سفارش {registration.order.number}: {registration.user} برای «{event.title}» پرداخت "
        "کرده، ولی ظرفیت پر شده یا ثبت‌نام لغو شده است. مبلغ باید برگردانده شود.",
    )


def cancel(registration: Registration, *, by_owner=False) -> Registration:
    """Leave an event. A paid seat can only be cancelled by the owner, who refunds it."""
    now = timezone.now()
    with transaction.atomic():
        event = _lock_event(registration.event_id)
        registration = Registration.objects.select_related("user", "order").get(pk=registration.pk)
        registration.event = event
        if registration.status not in Registration.ACTIVE_STATUSES:
            return registration
        was_paid = bool(registration.is_confirmed and registration.order)
        if was_paid and not by_owner:
            raise RegistrationError("برای انصراف از ثبت‌نام پرداخت‌شده با ما تماس بگیرید.")
        unpaid = registration.status == Registration.Status.PENDING
        registration.status = Registration.Status.CANCELLED
        registration.save(update_fields=["status"])
        _fill_seats(event, now)
    if unpaid:
        orders.cancel_unpaid(registration.order)
    send_sms(registration.user.mobile, "event_cancelled", {"token20": _title(event)})
    if was_paid:
        # Automatic refunds arrive with PAY-4 (sprint 5)
        email_owner(
            "لغو ثبت‌نام پرداخت‌شده",
            f"سفارش {registration.order.number}: ثبت‌نام در «{event.title}» لغو شد. "
            "بازگشت وجه به‌صورت دستی انجام شود.",
        )
    return registration


def housekeeping() -> None:
    """Every minute: end unpaid holds and hand their seats to the waiting list.

    This also picks up a capacity the owner raised in the panel.
    """
    now = timezone.now()
    event_ids = (
        Registration.objects.filter(
            Q(status=Registration.Status.WAITLIST)
            | Q(status=Registration.Status.PENDING, hold_expires_at__lte=now)
        )
        .values_list("event_id", flat=True)
        .distinct()
    )
    for event_id in list(event_ids):
        with transaction.atomic():
            event = _lock_event(event_id)
            unpaid = _expire_holds(event, now)
            _fill_seats(event, now)
        _cancel_orders(unpaid)


def send_reminders(now=None) -> int:
    """Every 5 minutes: SMS one day and 30 minutes before the event (spec section 8.3)."""
    now = now or timezone.now()
    day, half_hour = timedelta(days=1), timedelta(minutes=30)
    sent = 0
    for field, lead in (("reminded_1d_at", day), ("reminded_30m_at", half_hour)):
        due = Registration.objects.filter(
            status=Registration.Status.PAID,
            event__start_at__gt=now,
            event__start_at__lte=now + lead,
            **{f"{field}__isnull": True},
        ).select_related("user", "event")
        for registration in due:
            # A claimed row can never be sent twice, even if two workers overlap
            claimed = Registration.objects.filter(
                pk=registration.pk, **{f"{field}__isnull": True}
            ).update(**{field: now})
            if not claimed:
                continue
            event = registration.event
            joined_late = event.start_at - registration.created_at < day
            if field == "reminded_1d_at" and (joined_late or event.start_at - now <= half_hour):
                continue
            send_sms(
                registration.user.mobile,
                "event_reminder",
                {
                    "token": event.join_link or "-",
                    "token10": _when(event),
                    "token20": _title(event),
                },
            )
            sent += 1
    return sent


def send_recordings(now=None) -> int:
    """Every 15 minutes: tell attendees once the recording of a finished event is up (EVT-4).

    The sent mark is on each registration: a page field would be overwritten
    whenever an older revision of the page is published.
    """
    now = now or timezone.now()
    due = (
        Registration.objects.filter(
            status=Registration.Status.PAID,
            recording_sent_at__isnull=True,
            event__end_at__lt=now,
            event__live=True,
        )
        .exclude(event__recording_url="")
        .select_related("user", "event")
    )
    sent = 0
    for registration in due:
        claimed = Registration.objects.filter(
            pk=registration.pk, recording_sent_at__isnull=True
        ).update(recording_sent_at=now)
        if claimed:
            send_sms(
                registration.user.mobile,
                "event_recording",
                {"token20": _title(registration.event)},
            )
            sent += 1
    return sent


def _title(event: EventPage) -> str:
    return " ".join(event.title.split()[:SMS_TITLE_WORDS])


def _when(event: EventPage) -> str:
    return jalali.format_datetime(event.start_at)
