"""Online class rooms: the foundation only (REPORT #051).

With ROOM_PROVIDER empty, "ورود به کلاس" opens the link typed on the event, as
before. Phase 2 adds a real provider (Skyroom is the suggestion) behind this
interface, creates rooms ahead of time and moves the SMS links to the site.
"""

from abc import ABC, abstractmethod

from django.conf import settings
from django.utils.module_loading import import_string


class RoomError(Exception):
    """The room service could not be reached or refused. The caller falls back."""


class RoomProvider(ABC):
    @abstractmethod
    def create_room(self, event) -> str:
        """Make a room for the event and return the service's id for it."""

    @abstractmethod
    def join_url(self, room_id: str, user, *, presenter: bool = False) -> str:
        """A personal link that only works for a short time, so it cannot be passed on."""

    @abstractmethod
    def check(self) -> str:
        """Reach the service with the configured key; a short report, or RoomError."""


class FakeRooms(RoomProvider):
    """For tests and local work: rooms that exist only as addresses."""

    def create_room(self, event) -> str:
        return f"room-{event.pk}"

    def join_url(self, room_id: str, user, *, presenter: bool = False) -> str:
        role = "presenter" if presenter else "attendee"
        return f"https://rooms.test/{room_id}?user={user.pk}&role={role}"

    def check(self) -> str:
        return "fake room service: nothing to reach"


def get_room_provider() -> RoomProvider | None:
    """The class named in ROOM_PROVIDER, or None while the feature is off."""
    path = settings.ROOM_PROVIDER
    return import_string(path)() if path else None
