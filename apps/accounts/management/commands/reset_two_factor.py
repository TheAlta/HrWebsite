from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts import two_factor
from apps.core.text import normalize_mobile


class Command(BaseCommand):
    help = (
        "Remove a staff member's authenticator app and backup codes, for a lost phone. "
        "They set up a new app at their next panel visit."
    )

    def add_arguments(self, parser):
        parser.add_argument("mobile")

    def handle(self, *args, mobile, **options):
        user = get_user_model().objects.filter(mobile=normalize_mobile(mobile)).first()
        if user is None:
            raise CommandError("No user with this mobile number.")
        removed = two_factor.reset(user)
        self.stdout.write(
            self.style.SUCCESS(f"Removed {removed} item(s). Next panel visit sets up again.")
        )
