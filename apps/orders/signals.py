from django.dispatch import Signal

# Sent once for every paid order. Domain apps listen and deliver what was sold.
# sender=Order class, kwargs: order
order_paid = Signal()
