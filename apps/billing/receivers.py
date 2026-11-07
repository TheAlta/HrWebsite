from django.dispatch import receiver

from apps.orders.signals import order_paid, order_reversed

from . import services


@receiver(order_paid)
def on_order_paid(sender, order, **kwargs):
    services.issue_invoice(order)
    services.mark_proforma_paid(order)


@receiver(order_reversed)
def on_order_reversed(sender, order, **kwargs):
    services.void_invoice(order)
