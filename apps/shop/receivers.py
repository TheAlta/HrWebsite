from django.dispatch import receiver

from apps.orders.signals import order_paid

from .services import deliver_order


@receiver(order_paid)
def on_order_paid(sender, order, **kwargs):
    deliver_order(order)
