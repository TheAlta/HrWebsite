from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.booking import calendars, services
from apps.core import jalali


class Command(BaseCommand):
    help = (
        "Read the calendars in BUSY_CALENDAR_URLS once and report, without saving anything. "
        "Run it before turning the feature on (BOOK-6)."
    )

    def handle(self, *args, **options):
        urls = calendars.feed_urls()
        if not urls:
            self.stdout.write("BUSY_CALENDAR_URLS is empty: the calendar feature is off.")
            return
        try:
            ranges = services.read_calendars()
        except calendars.FeedError as exc:
            raise CommandError(f"Reading failed: {exc}") from None
        self.stdout.write(
            self.style.SUCCESS(
                f"{len(urls)} calendar(s) read: {len(ranges)} busy time(s) "
                f"in the next {services.BOOKING_DAYS + 2} days."
            )
        )
        for start, end in ranges[:5]:
            local_end = timezone.localtime(end)
            self.stdout.write(f"  {jalali.format_datetime(start)} → {local_end:%H:%M}")
