import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.management import CommandError, call_command

from apps.events.models import EventPage

pytestmark = pytest.mark.django_db


def prepare(capsys, *args):
    call_command("prepare_load_test", *args)
    return capsys.readouterr().out


def test_it_makes_an_event_and_logged_in_customers(events_page, capsys):
    setup = json.loads(prepare(capsys, "--users", "3", "--capacity", "2"))
    event = EventPage.objects.get(slug="load-test-rush")
    assert setup["event"] == event.url
    assert event.capacity == 2 and event.price == 0
    assert len(setup["sessions"]) == 3
    assert Session.objects.filter(session_key__in=setup["sessions"]).count() == 3


def test_running_it_again_starts_clean(events_page, capsys):
    prepare(capsys, "--users", "3")
    prepare(capsys, "--users", "2")
    assert get_user_model().objects.filter(mobile__startswith="0990000").count() == 2
    assert EventPage.objects.filter(slug="load-test-rush").count() == 1


def test_cleanup_removes_everything(events_page, capsys):
    prepare(capsys, "--users", "3")
    prepare(capsys, "--cleanup")
    assert not EventPage.objects.filter(slug="load-test-rush").exists()
    assert not get_user_model().objects.filter(mobile__startswith="0990000").exists()


def test_refused_in_production(settings):
    settings.ALLOW_SEED_DEMO = False
    with pytest.raises(CommandError, match="production"):
        call_command("prepare_load_test")
