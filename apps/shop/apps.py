from django.apps import AppConfig


class ShopConfig(AppConfig):
    name = "apps.shop"
    label = "shop"
    verbose_name = "فروشگاه"

    def ready(self):
        from . import receivers  # noqa: F401
