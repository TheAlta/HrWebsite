import datetime as dt

import pytest
from django.contrib.auth import get_user_model

from apps.booking import services
from apps.booking.models import Availability, BookingPage, SessionType
from apps.content.models import HomePage


@pytest.fixture
def session_type(db):
    return SessionType.objects.create(
        title="جلسه آنلاین",
        mode=SessionType.Mode.ONLINE,
        duration_min=60,
        price=25_000_000,
        buffer_min=15,
        meeting_link="https://room.test/1",
    )


@pytest.fixture
def free_session(db):
    return SessionType.objects.create(
        title="گفت‌وگوی رایگان", mode=SessionType.Mode.PHONE, duration_min=20, price=0, buffer_min=10
    )


@pytest.fixture
def every_day(db):
    """Working hours on all seven days, so a free slot always exists."""
    for weekday in Availability.Weekday.values:
        Availability.objects.create(
            weekday=weekday, start_time=dt.time(9, 0), end_time=dt.time(17, 0)
        )


@pytest.fixture
def customer(db):
    return get_user_model().objects.create_user("09121234567")


@pytest.fixture
def other_customer(db):
    return get_user_model().objects.create_user("09351112233")


@pytest.fixture
def first_slot(session_type, every_day):
    return services.free_slots(session_type)[0].slots[0]


@pytest.fixture
def far_slot(session_type, every_day):
    """A slot more than 24 hours away, which the customer may still change."""
    return services.free_slots(session_type)[3].slots[0]


@pytest.fixture
def booking_page(db):
    home = HomePage.objects.get()
    page = BookingPage(title="رزرو جلسه", slug="booking")
    home.add_child(instance=page)
    return page
