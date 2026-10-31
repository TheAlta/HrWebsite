from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from apps.orders.models import Order

from . import services
from .gateways import get_gateway
from .gateways.fake import simulate_payment
from .models import Payment


def begin_payment(request, order):
    """Send the customer to the bank, or back to the order page if no gateway answers."""

    def callback_url(gateway):
        return request.build_absolute_uri(reverse("payments:callback", args=[gateway]))

    try:
        return redirect(services.start_payment(order, callback_url))
    except services.PaymentUnavailable:
        messages.error(request, "اتصال به درگاه پرداخت ممکن نشد. لطفاً دوباره تلاش کنید.")
        return redirect("orders:detail", number=order.number)


@login_required
@require_POST
def pay(request, number):
    """Retry button on the order page."""
    order = get_object_or_404(Order, number=number, user=request.user)
    if not order.can_pay:
        return redirect("orders:detail", number=order.number)
    return begin_payment(request, order)


@csrf_exempt  # the bank posts here; nothing is trusted until `verify` confirms it
@require_http_methods(["GET", "POST"])
def callback(request, gateway):
    """The bank sends the customer back here (spec section 8.2, steps 4 to 7)."""
    if gateway not in settings.PAYMENT_GATEWAYS:
        raise Http404
    params = {**request.GET.dict(), **request.POST.dict()}
    authority = get_gateway(gateway).authority_from_callback(params)
    payment = Payment.objects.filter(gateway=gateway, authority=authority).first()
    if not authority or payment is None:
        raise Http404
    payment = services.settle(payment.pk)
    return redirect("orders:detail", number=payment.order.number)


@require_http_methods(["GET", "POST"])
def fake_bank(request, authority):
    """Stand-in for the bank's page; exists only when the fake gateway is configured."""
    if "fake" not in settings.PAYMENT_GATEWAY_ORDER:
        raise Http404
    if request.method == "POST":
        url = simulate_payment(authority, paid=request.POST.get("result") == "ok")
        if url is None or not url_has_allowed_host_and_scheme(
            url, {request.get_host()}, request.is_secure()
        ):
            raise Http404
        return redirect(url)
    return render(request, "payments/fake_bank.html", {"authority": authority})
