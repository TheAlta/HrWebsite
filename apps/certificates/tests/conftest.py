from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.events.models import Registration
from apps.events.tests.conftest import events_page, make_event  # noqa: F401


@pytest.fixture
def attendee(db):
    return get_user_model().objects.create_user("09121234567", first_name="سارا", last_name="محمدی")


@pytest.fixture
def nameless(db):
    return get_user_model().objects.create_user("09351112233")


@pytest.fixture
def ended_event(make_event):  # noqa: F811
    start = timezone.now() - timedelta(days=1)
    return make_event(
        title="دوره مصاحبه ساختاریافته",
        start_at=start,
        end_at=start + timedelta(hours=3),
        issues_certificate=True,
        instructor="آرزو زحمتبران",
    )


@pytest.fixture
def seat(ended_event):
    def make(user, status=Registration.Status.PAID):
        return Registration.objects.create(event=ended_event, user=user, status=status)

    return make


@pytest.fixture
def admin_client(client, django_user_model):
    client.force_login(django_user_model.objects.create_superuser("09120000000", password="x"))
    return client
