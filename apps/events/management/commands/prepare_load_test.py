"""Set up (or remove) a registration rush for loadtest/rush.py (spec section 4).

A free event with a small capacity, and many customers who are already logged
in. Prints what the script needs as JSON. Refused where ALLOW_SEED_DEMO is off,
which is production.
"""

import json
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.events.models import EventIndexPage, EventPage, Registration

SLUG = "load-test-rush"
MOBILE_PREFIX = "0990000"  # 0990000xxxx: a range no real customer has


class Command(BaseCommand):
    help = "Create a free event and logged-in customers for a load test, or --cleanup."

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=200)
        parser.add_argument("--capacity", type=int, default=50)
        parser.add_argument("--cleanup", action="store_true")

    def handle(self, *args, users, capacity, cleanup, **options):
        if not settings.ALLOW_SEED_DEMO:
            raise CommandError("Not here: ALLOW_SEED_DEMO is off (production).")
        self._remove()
        if cleanup:
            self.stderr.write("Load test data removed.")
            return
        index = EventIndexPage.objects.live().first()
        if index is None:
            raise CommandError("No events page yet: run seed_demo first.")
        start = timezone.now() + timedelta(days=7)
        event = EventPage(
            title="تست بار",
            slug=SLUG,
            kind=EventPage.Kind.WEBINAR,
            start_at=start,
            end_at=start + timedelta(hours=1),
            capacity=capacity,
            price=0,
        )
        index.add_child(instance=event)
        cookies = []
        for number in range(users):
            user = get_user_model().objects.create_user(f"{MOBILE_PREFIX}{number:04d}")
            session = SessionStore()
            session["_auth_user_id"] = str(user.pk)
            session["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
            session["_auth_user_hash"] = user.get_session_auth_hash()
            session.create()
            cookies.append(session.session_key)
        self.stdout.write(
            json.dumps({"event": event.url, "capacity": capacity, "sessions": cookies})
        )

    def _remove(self):
        Registration.objects.filter(event__slug=SLUG).delete()
        EventPage.objects.filter(slug=SLUG).delete()
        get_user_model().objects.filter(mobile__startswith=MOBILE_PREFIX).delete()
