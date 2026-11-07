from django.core.management.base import BaseCommand, CommandError

from apps.events.rooms import RoomError, get_room_provider


class Command(BaseCommand):
    help = "Reach the room service in ROOM_PROVIDER once and report. Run it before turning it on."

    def handle(self, *args, **options):
        provider = get_room_provider()
        if provider is None:
            self.stdout.write("ROOM_PROVIDER is empty: classes open the link typed on each event.")
            return
        try:
            report = provider.check()
        except RoomError as exc:
            raise CommandError(f"The room service failed: {exc}") from None
        self.stdout.write(self.style.SUCCESS(report))
