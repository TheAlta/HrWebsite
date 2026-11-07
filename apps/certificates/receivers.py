from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.events.models import Registration
from apps.orders.signals import order_reversed

from .services import revoke_for_order, revoke_for_registration


@receiver(order_reversed)
def on_order_reversed(sender, order, **kwargs):
    revoke_for_order(order)


@receiver(post_save, sender=Registration)
def on_registration_saved(sender, instance, **kwargs):
    """A registration the owner cancels, paid or free, takes its certificate with it."""
    if instance.status == Registration.Status.CANCELLED:
        revoke_for_registration(instance)
