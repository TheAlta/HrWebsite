"""The class entrance and the room service foundation (REPORT #051)."""

from datetime import timedelta

import pytest
from django.core.management import CommandError, call_command
from django.urls import reverse
from django.utils import timezone

from apps.events import rooms
from apps.events.models import EventPage, EventRoom, Registration

pytestmark = pytest.mark.django_db

FAKE = "apps.events.rooms.FakeRooms"


class BrokenRooms(rooms.FakeRooms):
    def create_room(self, event):
        raise rooms.RoomError("down")

    def check(self):
        raise rooms.RoomError("bad key")


@pytest.fixture
def attending(make_event, customer):
    event = make_event(start_at=timezone.now() + timedelta(hours=1))
    return Registration.objects.create(event=event, user=customer, status="paid")


def join(client, registration):
    return client.get(reverse("events:join", args=[registration.pk]))


def test_off_the_typed_link_is_used(client, attending):
    client.force_login(attending.user)
    response = join(client, attending)
    assert response.status_code == 302
    assert response.url == "https://room.test/1"
    assert response["Cache-Control"] == "private, no-store"
    assert not EventRoom.objects.exists()


def test_with_a_service_each_attendee_gets_a_personal_link(client, settings, attending):
    settings.ROOM_PROVIDER = FAKE
    client.force_login(attending.user)
    response = join(client, attending)
    assert (
        response.url
        == f"https://rooms.test/room-{attending.event.pk}?user={attending.user.pk}&role=attendee"
    )
    join(client, attending)
    assert EventRoom.objects.get().room_id == f"room-{attending.event.pk}"


def test_a_failing_service_falls_back_to_the_typed_link(client, settings, attending):
    settings.ROOM_PROVIDER = "apps.events.tests.test_rooms.BrokenRooms"
    client.force_login(attending.user)
    assert join(client, attending).url == "https://room.test/1"


def test_an_in_person_event_keeps_the_typed_link(client, settings, attending):
    settings.ROOM_PROVIDER = FAKE
    EventPage.objects.filter(pk=attending.event.pk).update(venue="تهران")
    client.force_login(attending.user)
    assert join(client, attending).url == "https://room.test/1"


def test_no_link_yet_sends_back_to_the_event(client, attending):
    EventPage.objects.filter(pk=attending.event.pk).update(join_link="")
    client.force_login(attending.user)
    response = join(client, attending)
    assert response.url == attending.event.url


def test_an_ended_event_has_no_entrance(client, attending):
    past = timezone.now() - timedelta(hours=3)
    EventPage.objects.filter(pk=attending.event.pk).update(
        start_at=past, end_at=past + timedelta(hours=1)
    )
    client.force_login(attending.user)
    assert join(client, attending).url == reverse("accounts:courses")


def test_only_the_confirmed_attendee_gets_in(client, attending, other_customer):
    client.force_login(other_customer)
    assert join(client, attending).status_code == 404
    Registration.objects.filter(pk=attending.pk).update(status="pending")
    client.force_login(attending.user)
    assert join(client, attending).status_code == 404


def test_the_entrance_needs_login(client, attending):
    assert reverse("accounts:login") in join(client, attending).url


def test_pages_link_the_entrance_not_the_room(client, attending):
    client.force_login(attending.user)
    entrance = reverse("events:join", args=[attending.pk])
    for url in (attending.event.url, reverse("accounts:courses")):
        content = client.get(url).content.decode()
        assert entrance in content
        assert "https://room.test/1" not in content


def test_with_a_service_the_entrance_shows_without_a_typed_link(client, settings, attending):
    EventPage.objects.filter(pk=attending.event.pk).update(join_link="")
    settings.ROOM_PROVIDER = FAKE
    client.force_login(attending.user)
    entrance = reverse("events:join", args=[attending.pk])
    assert entrance in client.get(reverse("accounts:courses")).content.decode()


def test_check_rooms_reports_off(settings, capsys):
    settings.ROOM_PROVIDER = ""
    call_command("check_rooms")
    assert "empty" in capsys.readouterr().out


def test_check_rooms_reaches_the_service(settings, capsys):
    settings.ROOM_PROVIDER = FAKE
    call_command("check_rooms")
    assert "fake room service" in capsys.readouterr().out


def test_check_rooms_fails_loudly(settings):
    settings.ROOM_PROVIDER = "apps.events.tests.test_rooms.BrokenRooms"
    with pytest.raises(CommandError, match="bad key"):
        call_command("check_rooms")
