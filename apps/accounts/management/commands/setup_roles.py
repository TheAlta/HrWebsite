from django.core.management.base import BaseCommand

from apps.accounts.roles import setup_roles


class Command(BaseCommand):
    help = "Create or update the panel roles (ADM-3). Safe to run on every deploy."

    def handle(self, *args, **options):
        names = [group.name for group in setup_roles()]
        self.stdout.write(self.style.SUCCESS(f"Roles ready: {', '.join(names)}"))
