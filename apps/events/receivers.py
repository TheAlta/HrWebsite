from django.dispatch import receiver

from apps.orders.signals import order_paid, order_reversed

from .services import confirm_registrations_for_order, release_registrations_for_order


@receiver(order_paid)
def on_order_paid(sender, order, **kwargs):
    confirm_registrations_for_order(order)


@receiver(order_reversed)
def on_order_reversed(sender, order, **kwargs):
    release_registrations_for_order(order)
