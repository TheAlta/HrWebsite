"""The bar above the header for the next free course or webinar (REPORT #058)."""

from datetime import timedelta

import pytest
from django.utils import timezone
from wagtail.models import Site

from apps.content.models import SiteSettings
from apps.events.models import EventPage
from apps.events.templatetags.event_tags import BAR_CLOSED_COOKIE

pytestmark = pytest.mark.django_db

BAR = 'class="event-bar"'


def test_the_next_free_event_shows_above_every_page(client, make_event):
    make_event(title="وبینار دیرتر", price=0, start_at=timezone.now() + timedelta(days=20))
    make_event(title="وبینار زودتر", price=0, start_at=timezone.now() + timedelta(days=3))
    html = client.get("/").content.decode()
    assert BAR in html
    assert "وبینار زودتر" in html.split(BAR)[1].split("</aside>")[0]


@pytest.mark.parametrize(
    "fields",
    [
        {"price": 5_000_000},  # paid
        {"price": 0, "start_at": timezone.now() - timedelta(days=1)},  # already held
        {"price": 0, "kind": EventPage.Kind.TALK},  # a talk is not registered for
    ],
)
def test_only_free_events_still_to_come_and_open_to_register(client, make_event, fields):
    make_event(**fields)
    assert BAR not in client.get("/").content.decode()


def test_closing_it_keeps_it_away_for_that_event_only(client, make_event):
    event = make_event(price=0)
    client.cookies[BAR_CLOSED_COOKIE] = str(event.pk)
    assert BAR not in client.get("/").content.decode()
    client.cookies[BAR_CLOSED_COOKIE] = str(event.pk + 1000)  # an older event's choice
    assert BAR in client.get("/").content.decode()


def test_the_owner_can_turn_it_off(client, make_event):
    make_event(price=0)
    settings = SiteSettings.for_site(Site.objects.get(is_default_site=True))
    settings.show_event_bar = False
    settings.save()
    assert BAR not in client.get("/").content.decode()
