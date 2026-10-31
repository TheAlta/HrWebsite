from django.dispatch import receiver

from apps.orders.signals import order_paid

from .services import confirm_registrations_for_order


@receiver(order_paid)
def on_order_paid(sender, order, **kwargs):
    confirm_registrations_for_order(order)
