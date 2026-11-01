from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.http import hashed_ip

from . import services
from .forms import CodeForm, MobileForm


def _next_url(request):
    url = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(url, {request.get_host()}, request.is_secure()):
        return url
    return reverse("accounts:account")


@require_http_methods(["GET", "POST"])
def login_view(request):
    """Step 1: mobile number → SMS code. Step 2 is `verify_view`."""
    if request.user.is_authenticated:
        return redirect(_next_url(request))
    form = MobileForm(request.POST or None)
    error = None
    if request.method == "POST" and form.is_valid():
        mobile = form.cleaned_data["mobile"]
        try:
            services.request_code(mobile, hashed_ip(request))
        except services.OTPError as exc:
            error = str(exc)
        else:
            context = {
                "form": CodeForm(initial={"mobile": mobile}),
                "mobile": mobile,
                "next": _next_url(request),
            }
            return render(request, _template(request, "code_step"), context)
    context = {"form": form, "error": error, "next": _next_url(request)}
    return render(request, _template(request, "mobile_step"), context)


@require_POST
def verify_view(request):
    form = CodeForm(request.POST)
    error = None
    if form.is_valid():
        try:
            user = services.verify_code(form.cleaned_data["mobile"], form.cleaned_data["code"])
        except services.OTPError as exc:
            error = str(exc)
        else:
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            url = _next_url(request)
            if request.htmx:
                response = render(request, "accounts/includes/redirect.html")
                response["HX-Redirect"] = url
                return response
            return redirect(url)
    context = {
        "form": form,
        "error": error,
        "mobile": request.POST.get("mobile", ""),
        "next": _next_url(request),
    }
    return render(request, _template(request, "code_step"), context)


@require_POST
def logout_view(request):
    logout(request)
    return redirect("/")


@login_required
def account_view(request):
    """What the customer bought; the full user panel arrives with USER-2 (sprint 5)."""
    from apps.booking.models import Booking
    from apps.booking.services import can_change
    from apps.events.models import Registration
    from apps.orders.models import Order
    from apps.shop.models import DownloadToken

    bookings = list(
        Booking.objects.filter(user=request.user)
        .exclude(status=Booking.Status.EXPIRED)
        .select_related("session_type", "order")[:20]
    )
    for booking in bookings:
        booking.changeable = can_change(booking)
    context = {
        "bookings": bookings,
        "registrations": Registration.objects.filter(
            user=request.user, status__in=Registration.ACTIVE_STATUSES
        ).select_related("event", "order")[:20],
        "downloads": DownloadToken.objects.filter(user=request.user).select_related("product")[:20],
        "orders": Order.objects.filter(user=request.user)[:10],
    }
    return render(request, "accounts/account.html", context)


def _template(request, step):
    # HTMX swaps only the card; a normal request gets the full page
    return f"accounts/includes/{step}.html" if request.htmx else "accounts/login.html"
