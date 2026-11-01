from django.dispatch import Signal

# Sent once for every paid order. Domain apps listen and deliver what was sold.
# sender=Order class, kwargs: order
order_paid = Signal()

# Sent when a paid order is refunded or an unpaid one is cancelled from the panel, inside
# a transaction that holds the order row. Domain apps take back what they delivered.
# sender=Order class, kwargs: order
order_reversed = Signal()
