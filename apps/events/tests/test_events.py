import threading
from datetime import timedelta

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.urls import reverse
from django.utils import timezone
from wagtail.test.utils.form_data import inline_formset, nested_form_data, rich_text

from apps.booking.models import TimeOff
from apps.content.models import SiteSettings
from apps.core import jalali
from apps.crm.models import Lead
from apps.events import services
from apps.events.models import EventPage, EventSession, Registration, SpeakingPage
from apps.notifications.testing import CapturingSMS
from apps.orders import services as orders
from apps.orders.models import Order

pytestmark = pytest.mark.django_db

Status = Registration.Status


def pay(registration):
    with transaction.atomic():
        orders.mark_paid(registration.order)
    orders.fulfil(registration.order)
    registration.refresh_from_db()


def expire_hold(registration):
    Registration.objects.filter(pk=registration.pk).update(
        hold_expires_at=timezone.now() - timedelta(minutes=1)
    )


def last_sms(user):
    return [m for m in CapturingSMS.outbox if m["to"] == user.mobile][-1]


def set_owner_email():
    site_settings = SiteSettings.for_default_site()
    site_settings.notify_email = "owner@example.com"
    site_settings.save()


# --- registration -----------------------------------------------------------------------


def test_free_event_confirms_at_once(free_event, customer):
    registration = services.register(customer, free_event)
    assert registration.status == Status.PAID
    assert registration.order is None


def test_paid_event_holds_seat_and_creates_order(paid_event, customer):
    registration = services.register(customer, paid_event)
    assert registration.status == Status.PENDING
    assert registration.order.total == 10_000_000
    assert registration.order.items.get().item == registration
    assert 14 * 60 < (registration.hold_expires_at - timezone.now()).total_seconds() <= 15 * 60
    assert services.seats_left(paid_event) == 0


def test_payment_confirms_and_sends_join_link(paid_event, customer):
    registration = services.register(customer, paid_event)
    pay(registration)
    assert registration.status == Status.PAID
    assert registration.hold_expires_at is None
    assert last_sms(customer)["params"]["token"] == "https://room.test/1"


def test_repeated_register_returns_the_same_row(paid_event, customer):
    first = services.register(customer, paid_event)
    assert services.register(customer, paid_event) == first
    assert Order.objects.count() == 1


def test_registration_closes_at_start(make_event, customer):
    event = make_event(start_at=timezone.now() - timedelta(minutes=1))
    with pytest.raises(services.RegistrationError):
        services.register(customer, event)


def test_talks_have_no_registration(make_event, customer):
    with pytest.raises(services.RegistrationError):
        services.register(customer, make_event(kind=EventPage.Kind.TALK))


def test_no_limit_when_capacity_is_empty(make_event, customer, other_customer):
    event = make_event(capacity=None)
    assert services.register(customer, event).status == Status.PAID
    assert services.register(other_customer, event).status == Status.PAID
    assert services.seats_left(event) is None


def test_database_refuses_two_active_rows_for_one_customer(free_event, customer):
    services.register(customer, free_event)
    with pytest.raises(IntegrityError), transaction.atomic():
        Registration.objects.create(event=free_event, user=customer, status=Status.WAITLIST)


# --- capacity and waiting list ----------------------------------------------------------


def test_full_event_sends_customer_to_waiting_list(paid_event, customer, other_customer):
    services.register(customer, paid_event)
    registration = services.register(other_customer, paid_event)
    assert registration.status == Status.WAITLIST
    assert registration.order is None
    assert last_sms(other_customer)["template"] == "event-waitlisted"


def test_waiting_list_keeps_its_turn_over_new_customers(
    free_event, customer, other_customer, third_customer
):
    first = services.register(customer, free_event)
    waiting = services.register(other_customer, free_event)
    Registration.objects.filter(pk=first.pk).update(status=Status.CANCELLED)
    newcomer = services.register(third_customer, free_event)
    waiting.refresh_from_db()
    assert waiting.status == Status.PAID
    assert newcomer.status == Status.WAITLIST


def test_expired_hold_goes_to_the_next_in_line(paid_event, customer, other_customer):
    holder = services.register(customer, paid_event)
    waiting = services.register(other_customer, paid_event)
    expire_hold(holder)
    services.housekeeping()

    holder.refresh_from_db()
    waiting.refresh_from_db()
    assert holder.status == Status.EXPIRED
    assert holder.order.status == Order.Status.CANCELLED
    assert waiting.status == Status.PENDING
    assert waiting.order.total == 10_000_000
    assert 23 * 3600 < (waiting.hold_expires_at - timezone.now()).total_seconds() <= 24 * 3600
    assert last_sms(other_customer)["template"] == "event-seat-open"


def test_offer_ends_before_the_event_starts(make_event, customer, other_customer):
    event = make_event(price=1_000, capacity=1, start_at=timezone.now() + timedelta(hours=3))
    holder = services.register(customer, event)
    waiting = services.register(other_customer, event)
    expire_hold(holder)
    services.housekeeping()
    waiting.refresh_from_db()
    assert waiting.hold_expires_at == event.start_at


def test_ignored_offer_moves_to_the_next_person(
    paid_event, customer, other_customer, third_customer
):
    holder = services.register(customer, paid_event)
    second = services.register(other_customer, paid_event)
    third = services.register(third_customer, paid_event)
    expire_hold(holder)
    services.housekeeping()
    expire_hold(second)
    services.housekeeping()
    second.refresh_from_db()
    third.refresh_from_db()
    assert second.status == Status.EXPIRED
    assert third.status == Status.PENDING


def test_raising_capacity_fills_from_the_waiting_list(free_event, customer, other_customer):
    services.register(customer, free_event)
    waiting = services.register(other_customer, free_event)
    EventPage.objects.filter(pk=free_event.pk).update(capacity=2)
    services.housekeeping()
    waiting.refresh_from_db()
    assert waiting.status == Status.PAID


def test_no_offers_after_the_event_started(paid_event, customer, other_customer):
    holder = services.register(customer, paid_event)
    waiting = services.register(other_customer, paid_event)
    expire_hold(holder)
    EventPage.objects.filter(pk=paid_event.pk).update(
        start_at=timezone.now() - timedelta(minutes=1)
    )
    services.housekeeping()
    waiting.refresh_from_db()
    assert waiting.status == Status.WAITLIST


def test_customer_can_register_again_after_hold_expired(paid_event, customer):
    first = services.register(customer, paid_event)
    expire_hold(first)
    second = services.register(customer, paid_event)
    assert second != first
    assert second.status == Status.PENDING


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_two_customers_racing_for_the_last_seat(make_event, customer, other_customer):
    """Real parallel transactions: one gets the seat, the other waits in line."""
    event = make_event(price=10_000_000, capacity=1)
    barrier = threading.Barrier(2)
    results = []

    def attempt(user):
        barrier.wait()
        try:
            results.append(services.register(user, event).status)
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt, args=[u]) for u in (customer, other_customer)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == sorted([Status.PENDING, Status.WAITLIST])
    assert services.taken_seats(event) == 1


# --- late payments ----------------------------------------------------------------------


def test_late_payment_keeps_a_seat_that_is_still_free(paid_event, customer):
    registration = services.register(customer, paid_event)
    expire_hold(registration)
    services.housekeeping()
    pay(registration)
    assert registration.status == Status.PAID


def test_late_payment_on_a_taken_seat_alerts_the_owner(paid_event, customer, other_customer):
    set_owner_email()
    registration = services.register(customer, paid_event)
    expire_hold(registration)
    taker = services.register(other_customer, paid_event)
    pay(registration)
    taker.refresh_from_db()
    assert registration.status == Status.EXPIRED
    assert taker.status == Status.PENDING
    assert last_sms(customer)["template"] == "event-problem"


def test_late_payment_after_registering_again_changes_nothing(paid_event, customer):
    first = services.register(customer, paid_event)
    expire_hold(first)
    second = services.register(customer, paid_event)
    pay(first)
    second.refresh_from_db()
    assert first.status == Status.EXPIRED
    assert second.status == Status.PENDING
    assert last_sms(customer)["template"] == "event-problem"


def test_payment_after_cancel_is_reported(paid_event, customer):
    registration = services.register(customer, paid_event)
    services.cancel(registration)
    pay(registration)
    assert registration.status == Status.CANCELLED
    assert last_sms(customer)["template"] == "event-problem"


# --- cancelling -------------------------------------------------------------------------


def test_cancel_unpaid_seat_offers_it_to_the_next(paid_event, customer, other_customer):
    holder = services.register(customer, paid_event)
    waiting = services.register(other_customer, paid_event)
    services.cancel(holder)
    holder.refresh_from_db()
    waiting.refresh_from_db()
    assert holder.status == Status.CANCELLED
    assert holder.order.status == Order.Status.CANCELLED
    assert waiting.status == Status.PENDING


def test_customer_cannot_cancel_a_paid_seat(paid_event, customer):
    registration = services.register(customer, paid_event)
    pay(registration)
    with pytest.raises(services.RegistrationError):
        services.cancel(registration)
    registration.refresh_from_db()
    assert registration.status == Status.PAID


def test_owner_cancelling_a_paid_seat_tells_the_customer(paid_event, customer):
    registration = services.register(customer, paid_event)
    pay(registration)
    services.cancel(registration, by_owner=True)
    registration.refresh_from_db()
    assert registration.status == Status.CANCELLED
    assert last_sms(customer)["template"] == "event-cancelled"


def test_cancelling_twice_changes_nothing(free_event, customer):
    registration = services.register(customer, free_event)
    services.cancel(registration)
    count = len(CapturingSMS.outbox)
    services.cancel(registration)
    assert len(CapturingSMS.outbox) == count


# --- reminders and recordings -----------------------------------------------------------


def registered_long_ago(event, user):
    registration = Registration.objects.create(event=event, user=user, status=Status.PAID)
    Registration.objects.filter(pk=registration.pk).update(
        created_at=timezone.now() - timedelta(days=5)
    )
    return registration


def test_day_and_half_hour_reminders_each_once(make_event, customer):
    start = timezone.now() + timedelta(hours=23)
    registered_long_ago(make_event(start_at=start), customer)
    assert services.send_reminders() == 1
    assert services.send_reminders() == 0
    assert services.send_reminders(now=start - timedelta(minutes=20)) == 1
    assert services.send_reminders(now=start - timedelta(minutes=10)) == 0


def test_no_day_reminder_for_a_late_registration(make_event, customer):
    event = make_event(start_at=timezone.now() + timedelta(hours=23))
    services.register(customer, event)
    assert services.send_reminders() == 0


def test_only_confirmed_customers_get_reminders(make_event, customer):
    event = make_event(price=1_000, start_at=timezone.now() + timedelta(minutes=20))
    services.register(customer, event)
    assert services.send_reminders() == 0


def test_recording_sms_goes_out_once_after_the_event(make_event, customer):
    start = timezone.now() - timedelta(hours=3)
    event = make_event(start_at=start, recording_url="https://rec.test/1")
    registered_long_ago(event, customer)
    assert services.send_recordings() == 1
    assert services.send_recordings() == 0


def test_no_recording_sms_without_a_recording(make_event, customer):
    start = timezone.now() - timedelta(hours=3)
    registered_long_ago(make_event(start_at=start), customer)
    assert services.send_recordings() == 0


def test_republishing_an_old_revision_does_not_resend_the_recording(make_event, customer):
    start = timezone.now() - timedelta(hours=3)
    event = make_event(start_at=start, recording_url="https://rec.test/1")
    revision = event.save_revision()
    registered_long_ago(event, customer)
    services.send_recordings()
    revision.publish()
    assert services.send_recordings() == 0


def test_long_title_is_cut_for_the_sms_token(make_event):
    event = make_event(title=" ".join(["کلمه"] * 12))
    assert len(services._title(event).split()) == services.SMS_TITLE_WORDS


# --- pages ------------------------------------------------------------------------------


def test_join_link_is_hidden_until_the_seat_is_confirmed(client, paid_event, customer):
    assert "room.test" not in client.get(paid_event.url).content.decode()
    registration = services.register(customer, paid_event)
    client.force_login(customer)
    assert "room.test" not in client.get(paid_event.url).content.decode()
    pay(registration)
    assert "room.test" in client.get(paid_event.url).content.decode()


def test_recording_is_hidden_from_visitors(client, make_event, customer):
    start = timezone.now() - timedelta(hours=3)
    event = make_event(start_at=start, recording_url="https://rec.test/1")
    assert "rec.test" not in client.get(event.url).content.decode()
    registered_long_ago(event, customer)
    client.force_login(customer)
    assert "rec.test" in client.get(event.url).content.decode()


def register_url(event):
    return event.url + event.reverse_subpage("register")


def test_anonymous_register_goes_to_login(client, free_event):
    response = client.post(register_url(free_event))
    assert response.status_code == 302 and "/login" in response.url


def test_register_needs_post(client, free_event, customer):
    client.force_login(customer)
    assert client.get(register_url(free_event)).status_code == 405


def test_paid_register_redirects_to_the_bank(client, paid_event, customer):
    client.force_login(customer)
    response = client.post(register_url(paid_event))
    assert response.status_code == 302
    assert "/payments/" in response.url
    assert Registration.objects.get().status == Status.PENDING


def test_free_register_stays_on_the_page(client, free_event, customer):
    client.force_login(customer)
    assert client.post(register_url(free_event), follow=True).status_code == 200
    assert Registration.objects.get().status == Status.PAID


def test_customer_cancels_own_registration_only(client, free_event, customer, other_customer):
    registration = services.register(customer, free_event)
    url = reverse("events:cancel", args=[registration.pk])
    client.force_login(other_customer)
    assert client.post(url).status_code == 404
    client.force_login(customer)
    assert client.post(url).status_code == 302
    registration.refresh_from_db()
    assert registration.status == Status.CANCELLED


def test_account_page_lists_registrations(client, free_event, customer):
    services.register(customer, free_event)
    client.force_login(customer)
    content = client.get(reverse("accounts:account")).content.decode()
    assert free_event.title in content


def test_list_view_separates_upcoming_and_past(client, events_page, make_event):
    upcoming = make_event(title="رویداد آینده")
    past = make_event(title="رویداد گذشته", start_at=timezone.now() - timedelta(days=5))
    talk = make_event(title="سخنرانی همایش", kind=EventPage.Kind.TALK)
    response = client.get(events_page.url)
    assert list(response.context["upcoming"]) == [upcoming]
    assert list(response.context["past"]) == [past]
    assert talk.title not in response.content.decode()


def test_month_view_shows_events_and_sessions_on_their_days(client, events_page, make_event):
    start = timezone.now() + timedelta(days=2)
    event = make_event(start_at=start)
    EventSession.objects.create(event=event, start_at=start)
    day = jalali.to_jalali(start)
    response = client.get(events_page.url, {"view": "month", "y": day.year, "m": day.month})
    cells = [cell for week in response.context["weeks"] for cell in week if cell and cell.events]
    assert timezone.localdate(start) in [cell.date for cell in cells]
    assert len(response.context["month_events"]) == 1


@pytest.mark.parametrize("params", [{"y": "x"}, {"y": 1405, "m": 13}, {"y": 99999, "m": 1}])
def test_month_view_survives_bad_input(client, events_page, params):
    assert client.get(events_page.url, {"view": "month", **params}).status_code == 200


def test_month_navigation_crosses_the_year(client, events_page):
    response = client.get(events_page.url, {"view": "month", "y": 1405, "m": 12})
    assert response.context["next_month"] == {"y": 1406, "m": 1}
    response = client.get(events_page.url, {"view": "month", "y": 1405, "m": 1})
    assert response.context["previous_month"] == {"y": 1404, "m": 12}


def test_event_page_has_event_schema(client, free_event):
    assert '"@type": "Event"' in client.get(free_event.url).content.decode()


def test_end_before_start_is_refused(make_event):
    event = make_event()
    event.end_at = event.start_at - timedelta(hours=1)
    with pytest.raises(ValidationError):
        event.clean()


def test_speaking_page_lists_talks_and_takes_an_invitation(client, make_event):
    talk = make_event(title="سخنرانی همایش", kind=EventPage.Kind.TALK)
    page = SpeakingPage(title="سخنرانی‌ها", slug="speaking")
    talk.get_parent().get_parent().add_child(instance=page)
    assert talk.title in client.get(page.url).content.decode()

    response = client.post(
        reverse("crm:submit", args=["speaking"]),
        {
            "name": "علی رضایی",
            "mobile": "09121234567",
            "company": "همایش سالانه",
            "topic": "منابع انسانی",
            "audience_size": "200",
        },
    )
    assert response.status_code == 200
    lead = Lead.objects.get()
    assert lead.type == "speaking"
    assert lead.payload["topic"] == "منابع انسانی"


# --- panel ------------------------------------------------------------------------------


def test_panel_cancel_frees_the_seat(admin_client, free_event, customer, other_customer):
    registration = services.register(customer, free_event)
    waiting = services.register(other_customer, free_event)
    url = reverse("panel_registrations:edit", args=[registration.pk])
    assert admin_client.get(url).status_code == 200
    assert admin_client.post(url, {"status": Status.CANCELLED}).status_code == 302
    registration.refresh_from_db()
    waiting.refresh_from_db()
    assert registration.status == Status.CANCELLED
    assert waiting.status == Status.PAID
    assert not mail.outbox  # a free seat needs no refund


def test_panel_has_no_add_or_delete_for_registrations(admin_client, free_event, customer):
    registration = services.register(customer, free_event)
    assert admin_client.get(reverse("panel_registrations:add")).status_code == 302
    admin_client.post(reverse("panel_registrations:delete", args=[registration.pk]))
    assert Registration.objects.filter(pk=registration.pk).exists()


def test_panel_lists_registrations(admin_client, free_event, customer):
    services.register(customer, free_event)
    assert admin_client.get(reverse("panel_registrations:index")).status_code == 200


def test_panel_creates_an_event_with_shamsi_dates(admin_client, events_page):
    url = reverse("wagtailadmin_pages:add", args=["events", "eventpage", events_page.pk])
    assert admin_client.get(url).status_code == 200
    data = nested_form_data(
        {
            "title": "دوره تازه",
            "slug": "new-course",
            "kind": "course",
            "instructor": "",
            "summary": "",
            "body": rich_text(""),
            "start_at": "۱۴۰۵/۰۸/۲۰ ۱۸:۳۰",
            "end_at": "1405/08/20 20:30",
            "venue": "",
            "capacity": "10",
            "price": "0",
            "sessions": inline_formset(
                [{"title": "جلسه اول", "start_at": "۱۴۰۵/۰۸/۲۰ ۱۸:۳۰", "ORDER": "1"}]
            ),
            "comments": inline_formset([]),
            "action-publish": "action-publish",
        }
    )
    assert admin_client.post(url, data).status_code == 302
    event = EventPage.objects.get(slug="new-course")
    assert event.live
    assert jalali.format_input(event.start_at) == "۱۴۰۵/۰۸/۲۰ ۱۸:۳۰"
    assert event.sessions.count() == 1

    edit = admin_client.get(reverse("wagtailadmin_pages:edit", args=[event.pk]))
    assert "۱۴۰۵/۰۸/۲۰ ۱۸:۳۰" in edit.content.decode()


def test_time_off_is_entered_in_shamsi(admin_client):
    data = {
        "start": "۱۴۰۵/۱۲/۲۹ ۰۰:۰۰",
        "end": "۱۴۰۶/۰۱/۰۴ ۰۰:۰۰",
        "reason": "نوروز",
    }
    assert admin_client.post(reverse("panel_time_off:add"), data).status_code == 302
    row = TimeOff.objects.get()
    assert jalali.format_input(row.end) == "۱۴۰۶/۰۱/۰۴ ۰۰:۰۰"
    assert admin_client.get(reverse("panel_time_off:index")).status_code == 200


def test_event_with_registrations_cannot_be_deleted(admin_client, free_event, customer):
    services.register(customer, free_event)
    url = reverse("wagtailadmin_pages:delete", args=[free_event.pk])
    assert admin_client.get(url).status_code == 200
    admin_client.post(url)
    assert EventPage.objects.filter(pk=free_event.pk).exists()
