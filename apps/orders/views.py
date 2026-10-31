from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from .models import Order


@login_required
def detail(request, number):
    """Where the customer lands after the bank: outcome, reference and a retry button."""
    order = get_object_or_404(Order, number=number, user=request.user)
    payment = order.payments.filter(status="paid").first() or order.payments.first()
    return render(request, "orders/detail.html", {"order": order, "payment": payment})
