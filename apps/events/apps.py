from django.apps import AppConfig


class EventsConfig(AppConfig):
    name = "apps.events"
    label = "events"
    verbose_name = "رویدادها"

    def ready(self):
        from . import receivers  # noqa: F401
