from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.content.models import HomePage
from apps.events.models import EventIndexPage, EventPage


@pytest.fixture
def events_page(db):
    page = EventIndexPage(title="رویدادها", slug="events")
    HomePage.objects.get().add_child(instance=page)
    return page


@pytest.fixture
def make_event(events_page):
    counter = iter(range(1, 100))

    def make(**fields):
        start = fields.pop("start_at", timezone.now() + timedelta(days=10))
        event = EventPage(
            title=fields.pop("title", "دوره نمونه"),
            slug=f"event-{next(counter)}",
            start_at=start,
            end_at=fields.pop("end_at", start + timedelta(hours=2)),
            join_link=fields.pop("join_link", "https://room.test/1"),
            **fields,
        )
        events_page.add_child(instance=event)
        return event

    return make


@pytest.fixture
def paid_event(make_event):
    return make_event(price=10_000_000, capacity=1)


@pytest.fixture
def free_event(make_event):
    return make_event(price=0, capacity=1)


@pytest.fixture
def customer(db):
    return get_user_model().objects.create_user("09121234567")


@pytest.fixture
def other_customer(db):
    return get_user_model().objects.create_user("09351112233")


@pytest.fixture
def third_customer(db):
    return get_user_model().objects.create_user("09361112233")


@pytest.fixture
def admin_client(client, django_user_model):
    client.force_login(django_user_model.objects.create_superuser("09120000000", password="x"))
    return client
