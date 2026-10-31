from django.apps import AppConfig


class BookingConfig(AppConfig):
    name = "apps.booking"
    label = "booking"
    verbose_name = "رزرو جلسه"

    def ready(self):
        from . import receivers  # noqa: F401
