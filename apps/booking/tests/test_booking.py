import threading
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.booking import services
from apps.booking.models import Booking, SessionType
from apps.content.models import SiteSettings
from apps.notifications.testing import CapturingSMS
from apps.orders import services as orders
from apps.orders.models import Order, OrderItem

pytestmark = pytest.mark.django_db


def sms_templates(mobile="09121234567"):
    return [m["params"] for m in CapturingSMS.outbox if m["to"] == mobile]


def pay(booking):
    with transaction.atomic():
        orders.mark_paid(booking.order)
    orders.fulfil(booking.order)
    booking.refresh_from_db()


def confirmed(session_type, customer, start):
    booking = services.hold_slot(customer, session_type, start)
    pay(booking)
    return booking


def set_owner_email():
    site_settings = SiteSettings.for_default_site()
    site_settings.notify_email = "owner@example.com"
    site_settings.save()


# --- hold -------------------------------------------------------------------------------


def test_hold_locks_slot_and_creates_order(session_type, customer, first_slot):
    booking = services.hold_slot(customer, session_type, first_slot)
    assert booking.status == Booking.Status.HELD
    assert booking.end_at - booking.start_at == timedelta(minutes=60)
    assert booking.blocked_until - booking.end_at == timedelta(minutes=15)
    assert 14 * 60 < (booking.hold_expires_at - timezone.now()).total_seconds() <= 15 * 60
    order = booking.order
    assert (order.status, order.total) == ("pending", 25_000_000)
    item = order.items.get()
    assert item.item == booking and session_type.title in item.title_snapshot


def test_price_change_does_not_touch_an_existing_order(session_type, customer, first_slot):
    booking = services.hold_slot(customer, session_type, first_slot)
    SessionType.objects.filter(pk=session_type.pk).update(price=1)
    assert OrderItem.objects.get(order=booking.order).unit_price == 25_000_000


def test_time_never_offered_is_refused(session_type, customer, first_slot):
    with pytest.raises(services.BookingError):
        services.hold_slot(customer, session_type, first_slot + timedelta(minutes=7))


def test_taken_slot_is_refused(session_type, customer, other_customer, first_slot):
    services.hold_slot(customer, session_type, first_slot)
    with pytest.raises(services.BookingError):
        services.hold_slot(other_customer, session_type, first_slot)


def test_inactive_session_type_is_refused(session_type, customer, first_slot):
    SessionType.objects.filter(pk=session_type.pk).update(is_active=False)
    session_type.refresh_from_db()
    with pytest.raises(services.BookingError):
        services.hold_slot(customer, session_type, first_slot)


def test_own_hold_is_reused(session_type, customer, first_slot):
    first = services.hold_slot(customer, session_type, first_slot)
    assert services.hold_slot(customer, session_type, first_slot) == first
    assert Order.objects.count() == 1


def test_one_account_cannot_hold_many_slots(session_type, customer, every_day):
    slots = services.free_slots(session_type)[1].slots
    services.hold_slot(customer, session_type, slots[0])
    services.hold_slot(customer, session_type, slots[1])
    with pytest.raises(services.BookingError, match="پرداخت‌نشده"):
        services.hold_slot(customer, session_type, slots[2])


def test_database_refuses_overlap_even_without_the_code(session_type, customer, first_slot):
    booking = services.hold_slot(customer, session_type, first_slot)
    clash = Booking(
        user=customer,
        session_type=session_type,
        start_at=first_slot + timedelta(minutes=30),
        end_at=first_slot + timedelta(minutes=90),
        blocked_until=first_slot + timedelta(minutes=105),
        status=Booking.Status.CONFIRMED,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        clash.save()
    Booking.objects.filter(pk=booking.pk).update(status=Booking.Status.CANCELLED)
    clash.save()  # a cancelled booking no longer blocks


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_two_customers_racing_for_one_slot(session_type, customer, other_customer, first_slot):
    """Real parallel transactions: exactly one wins (spec section 14, concurrency)."""
    barrier = threading.Barrier(2)
    won, lost = [], []

    def attempt(user):
        barrier.wait()
        try:
            won.append(services.hold_slot(user, session_type, first_slot))
        except services.BookingError:
            lost.append(user)
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt, args=(u,)) for u in (customer, other_customer)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert (len(won), len(lost)) == (1, 1)
    assert Booking.objects.filter(status=Booking.Status.HELD).count() == 1


# --- expiry ---------------------------------------------------------------------------------


def expire(booking):
    Booking.objects.filter(pk=booking.pk).update(
        hold_expires_at=timezone.now() - timedelta(seconds=1)
    )


def test_expired_hold_is_released_and_order_cancelled(session_type, customer, first_slot):
    booking = services.hold_slot(customer, session_type, first_slot)
    expire(booking)
    assert services.release_expired() == 1
    booking.refresh_from_db()
    booking.order.refresh_from_db()
    assert booking.status == Booking.Status.EXPIRED
    assert booking.order.status == "cancelled"


def test_new_customer_can_take_an_expired_hold_at_once(
    session_type, customer, other_customer, first_slot
):
    expire(services.hold_slot(customer, session_type, first_slot))
    booking = services.hold_slot(other_customer, session_type, first_slot)
    assert booking.user == other_customer


# --- payment outcome ------------------------------------------------------------------------


def test_paid_order_confirms_booking_and_notifies(session_type, customer, first_slot, demo_site):
    set_owner_email()
    booking = services.hold_slot(customer, session_type, first_slot)
    pay(booking)
    assert booking.status == Booking.Status.CONFIRMED
    assert booking.hold_expires_at is None
    assert booking.meeting_link == "https://room.test/1"
    sent = [m for m in CapturingSMS.outbox if m["template"] == "booking-confirmed"]
    assert len(sent) == 1 and sent[0]["params"]["token"] == booking.order.number
    assert "رزرو جدید" in mail.outbox[-1].subject


def test_free_session_needs_no_payment(free_session, customer, every_day):
    start = services.free_slots(free_session)[0].slots[0]
    booking = services.hold_slot(customer, free_session, start)
    assert booking.status == Booking.Status.CONFIRMED


def test_late_payment_reclaims_a_slot_still_free(session_type, customer, first_slot):
    booking = services.hold_slot(customer, session_type, first_slot)
    expire(booking)
    services.release_expired()
    booking.order.refresh_from_db()
    pay(booking)
    assert booking.status == Booking.Status.CONFIRMED


def test_late_payment_for_a_lost_slot_is_reported(
    session_type, customer, other_customer, first_slot, demo_site
):
    set_owner_email()
    booking = services.hold_slot(customer, session_type, first_slot)
    expire(booking)
    winner = services.hold_slot(other_customer, session_type, first_slot)
    booking.order.refresh_from_db()
    pay(booking)
    assert booking.status == Booking.Status.EXPIRED
    assert Booking.objects.get(pk=winner.pk).status == Booking.Status.HELD
    assert "پرداخت بعد از انقضای" in mail.outbox[-1].subject
    assert any(m["template"] == "booking-problem" for m in CapturingSMS.outbox)
    booking.order.refresh_from_db()
    assert booking.order.fulfilled_at  # handled once, not retried for ever


def test_payment_after_owner_cancelled_does_not_revive(session_type, customer, first_slot):
    booking = services.hold_slot(customer, session_type, first_slot)
    services.cancel(booking, by_owner=True)
    booking.order.refresh_from_db()
    pay(booking)
    assert booking.status == Booking.Status.CANCELLED
    assert any(m["template"] == "booking-problem" for m in CapturingSMS.outbox)


# --- cancel and reschedule ------------------------------------------------------------------


def test_customer_cancels_a_day_before(session_type, customer, far_slot, demo_site):
    set_owner_email()
    booking = confirmed(session_type, customer, far_slot)
    services.cancel(booking)
    assert booking.status == Booking.Status.CANCELLED
    assert any(m["template"] == "booking-cancelled" for m in CapturingSMS.outbox)
    assert "بازگشت وجه" in mail.outbox[-1].body
    assert services.is_free(session_type, far_slot)  # the time is open again


def test_no_cancel_inside_24_hours(session_type, customer, first_slot):
    booking = confirmed(session_type, customer, first_slot)
    with pytest.raises(services.BookingError):
        services.cancel(booking)
    services.cancel(booking, by_owner=True)  # the owner may
    assert booking.status == Booking.Status.CANCELLED


def test_reschedule_moves_the_session(session_type, customer, far_slot):
    booking = confirmed(session_type, customer, far_slot)
    Booking.objects.filter(pk=booking.pk).update(reminded_24h_at=timezone.now())
    booking.refresh_from_db()
    target = services.free_slots(session_type)[5].slots[0]
    services.reschedule(booking, target)
    booking.refresh_from_db()
    assert booking.start_at == target
    assert booking.blocked_until == target + timedelta(minutes=75)
    assert booking.reminded_24h_at is None
    assert services.is_free(session_type, far_slot)


def test_reschedule_to_a_nearby_overlapping_time_of_its_own(session_type, customer, far_slot):
    """The next slot may touch the session's own buffer; it must not block itself."""
    booking = confirmed(session_type, customer, far_slot)
    days = services.free_slots(session_type, ignore=booking)
    day = next(d for d in days if far_slot in d.slots)
    services.reschedule(booking, day.slots[day.slots.index(far_slot) + 1])
    assert booking.status == Booking.Status.CONFIRMED


def test_reschedule_rules(session_type, customer, first_slot, far_slot):
    late = confirmed(session_type, customer, first_slot)
    with pytest.raises(services.BookingError):
        services.reschedule(late, far_slot)
    booking = confirmed(session_type, customer, far_slot)
    with pytest.raises(services.BookingError):
        services.reschedule(booking, far_slot + timedelta(minutes=7))


# --- reminders ------------------------------------------------------------------------------


def book_ahead(session_type, customer, start, *, booked_days_before=5):
    booking = confirmed(session_type, customer, start)
    Booking.objects.filter(pk=booking.pk).update(
        created_at=start - timedelta(days=booked_days_before)
    )
    CapturingSMS.outbox.clear()
    return booking


def reminders():
    return [m for m in CapturingSMS.outbox if m["template"] == "booking-reminder"]


def test_reminders_fire_once_each(session_type, customer, far_slot):
    book_ahead(session_type, customer, far_slot)
    day_before = far_slot - timedelta(hours=23)
    assert services.send_reminders(now=day_before) == 1
    assert services.send_reminders(now=day_before) == 0
    hour_before = far_slot - timedelta(minutes=50)
    assert services.send_reminders(now=hour_before) == 1
    assert services.send_reminders(now=hour_before) == 0
    assert len(reminders()) == 2
    assert reminders()[0]["params"]["token20"] == "https://room.test/1"


def test_session_booked_today_skips_the_day_before_reminder(session_type, customer, far_slot):
    book_ahead(session_type, customer, far_slot, booked_days_before=0)
    assert services.send_reminders(now=far_slot - timedelta(hours=5)) == 0
    assert services.send_reminders(now=far_slot - timedelta(minutes=30)) == 1


def test_worker_outage_sends_one_reminder_not_two(session_type, customer, far_slot):
    book_ahead(session_type, customer, far_slot)
    assert services.send_reminders(now=far_slot - timedelta(minutes=30)) == 1


def test_no_reminder_for_cancelled_session(session_type, customer, far_slot):
    booking = book_ahead(session_type, customer, far_slot)
    services.cancel(booking)
    assert services.send_reminders(now=far_slot - timedelta(hours=2)) == 0


def test_finished_sessions_are_closed(session_type, customer, first_slot):
    booking = confirmed(session_type, customer, first_slot)
    Booking.objects.filter(pk=booking.pk).update(end_at=timezone.now() - timedelta(minutes=1))
    services.housekeeping()
    booking.refresh_from_db()
    assert booking.status == Booking.Status.DONE


def test_schedules_are_registered():
    from django_q.models import Schedule

    funcs = set(Schedule.objects.values_list("func", flat=True))
    assert {
        "apps.booking.services.housekeeping",
        "apps.booking.services.send_reminders",
        "apps.payments.services.reconcile",
    } <= funcs


# --- pages --------------------------------------------------------------------------------


def test_booking_journey_end_to_end(client, session_type, customer, first_slot, booking_page):
    """Type → time → login → hold → bank → confirmed (spec section 8.1)."""
    assert session_type.title in client.get("/booking/").content.decode()
    slots_html = client.get(f"/booking/{session_type.pk}/").content.decode()
    start = int(first_slot.timestamp())
    assert f'value="{start}"' in slots_html

    confirm_url = f"/booking/{session_type.pk}/confirm/?start={start}"
    response = client.get(confirm_url)
    assert response.status_code == 302 and "/account/login/" in response.url

    client.force_login(customer)
    assert "پرداخت و ثبت رزرو" in client.get(confirm_url).content.decode()
    bank_url = client.post(confirm_url).url
    callback_url = client.post(bank_url, {"result": "ok"}).url
    order_url = client.get(callback_url).url
    assert "پرداخت با موفقیت انجام شد" in client.get(order_url).content.decode()

    booking = Booking.objects.get()
    assert booking.status == Booking.Status.CONFIRMED
    assert session_type.title in client.get("/account/").content.decode()


def test_taken_time_returns_to_the_calendar_with_a_message(
    client, session_type, customer, other_customer, first_slot, booking_page
):
    services.hold_slot(other_customer, session_type, first_slot)
    client.force_login(customer)
    url = f"/booking/{session_type.pk}/confirm/?start={int(first_slot.timestamp())}"
    response = client.post(url, follow=True)
    assert "زمان دیگری انتخاب کنید" in response.content.decode()


def test_bad_start_value_is_404(client, session_type, customer, booking_page):
    client.force_login(customer)
    assert client.get(f"/booking/{session_type.pk}/confirm/?start=abc").status_code == 404
    assert client.get(f"/booking/{session_type.pk}/confirm/").status_code == 404
    assert client.get("/booking/99999/").status_code == 404


def test_free_session_journey(client, free_session, customer, every_day, booking_page):
    start = int(services.free_slots(free_session)[0].slots[0].timestamp())
    client.force_login(customer)
    response = client.post(f"/booking/{free_session.pk}/confirm/?start={start}", follow=True)
    assert "ثبت شد" in response.content.decode()


def test_customer_can_change_only_their_own_booking(
    client, session_type, customer, other_customer, far_slot
):
    booking = confirmed(session_type, customer, far_slot)
    client.force_login(other_customer)
    assert client.post(f"/account/bookings/{booking.pk}/cancel/").status_code == 404
    assert client.get(f"/account/bookings/{booking.pk}/reschedule/").status_code == 404


def test_cancel_and_reschedule_pages(client, session_type, customer, far_slot):
    booking = confirmed(session_type, customer, far_slot)
    client.force_login(customer)
    page = client.get(f"/account/bookings/{booking.pk}/reschedule/").content.decode()
    assert 'name="start"' in page
    target = services.free_slots(session_type, ignore=booking)[5].slots[0]
    response = client.post(
        f"/account/bookings/{booking.pk}/reschedule/", {"start": int(target.timestamp())}
    )
    assert response.url == "/account/"
    booking.refresh_from_db()
    assert booking.start_at == target
    client.post(f"/account/bookings/{booking.pk}/cancel/")
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED


def test_cancel_needs_post_and_login(client, session_type, customer, far_slot):
    booking = confirmed(session_type, customer, far_slot)
    assert client.post(f"/account/bookings/{booking.pk}/cancel/").status_code == 302
    client.force_login(customer)
    assert client.get(f"/account/bookings/{booking.pk}/cancel/").status_code == 405
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED


# --- panel ----------------------------------------------------------------------------------


@pytest.fixture
def admin_client(client):
    admin = get_user_model().objects.create_superuser("09120000000", password="x-pass-123")
    client.force_login(admin)
    return client


def test_panel_cancel_frees_the_slot_and_tells_the_customer(
    admin_client, session_type, customer, far_slot
):
    booking = confirmed(session_type, customer, far_slot)
    CapturingSMS.outbox.clear()
    response = admin_client.post(
        f"/panel/bookings/edit/{booking.pk}/",
        {"status": "cancelled", "meeting_link": "", "admin_note": ""},
    )
    assert response.status_code == 302, response.content.decode()[:1500]
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED
    assert any(m["template"] == "booking-cancelled" for m in CapturingSMS.outbox)


def test_panel_cannot_reactivate_an_ended_booking(admin_client, session_type, customer, far_slot):
    booking = confirmed(session_type, customer, far_slot)
    services.cancel(booking)
    response = admin_client.post(
        f"/panel/bookings/edit/{booking.pk}/",
        {"status": "confirmed", "meeting_link": "", "admin_note": ""},
    )
    assert response.status_code == 200  # the form refuses it
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED
