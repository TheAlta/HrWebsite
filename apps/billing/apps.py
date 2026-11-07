from django.apps import AppConfig


class BillingConfig(AppConfig):
    name = "apps.billing"
    label = "billing"
    verbose_name = "فاکتور و پیش‌فاکتور"

    def ready(self):
        from . import receivers  # noqa: F401
