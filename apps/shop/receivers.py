from django.dispatch import receiver

from apps.orders.signals import order_paid, order_reversed

from .services import deliver_order, reverse_order


@receiver(order_paid)
def on_order_paid(sender, order, **kwargs):
    deliver_order(order)


@receiver(order_reversed)
def on_order_reversed(sender, order, **kwargs):
    reverse_order(order)
