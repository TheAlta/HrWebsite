from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST
from django_otp import login as otp_login
from django_otp import match_token

from apps.core.http import hashed_ip

from . import services, two_factor
from .forms import CodeForm, MobileForm, ProfileForm, TwoFactorForm

PER_PAGE = 10


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


def _page(request, rows):
    """One page of a list. A bad page number shows the nearest real page."""
    return Paginator(rows, PER_PAGE).get_page(request.GET.get("page"))


@login_required
def account_view(request):
    """The start of the user panel (USER-2): what needs attention, and what is next."""
    from apps.booking.models import Booking
    from apps.events.models import Registration
    from apps.orders.models import Order

    now = timezone.now()
    context = {
        "unpaid": Order.objects.filter(
            user=request.user, status=Order.Status.PENDING, total__gt=0
        ).prefetch_related("items")[:5],
        "next_session": Booking.objects.filter(
            user=request.user, status=Booking.Status.CONFIRMED, start_at__gt=now
        )
        .select_related("session_type")
        .order_by("start_at")
        .first(),
        "next_course": Registration.objects.filter(
            user=request.user, status=Registration.Status.PAID, event__end_at__gt=now
        )
        .select_related("event")
        .order_by("event__start_at")
        .first(),
        "section": "home",
    }
    return render(request, "accounts/account.html", context)


@login_required
def orders_view(request):
    from apps.orders.models import Order

    rows = Order.objects.filter(user=request.user).prefetch_related("items")
    context = {"page_obj": _page(request, rows), "section": "orders"}
    return render(request, "accounts/orders.html", context)


@login_required
def invoices_view(request):
    from apps.billing.models import Invoice

    rows = Invoice.objects.filter(order__user=request.user).select_related("order")
    context = {"page_obj": _page(request, rows), "section": "invoices"}
    return render(request, "accounts/invoices.html", context)


@login_required
def sessions_view(request):
    from apps.booking.models import Booking
    from apps.booking.services import can_change

    rows = (
        Booking.objects.filter(user=request.user)
        .exclude(status=Booking.Status.EXPIRED)
        .select_related("session_type", "order")
    )
    page_obj = _page(request, rows)
    for booking in page_obj:
        booking.changeable = can_change(booking)
    context = {"page_obj": page_obj, "section": "sessions"}
    return render(request, "accounts/sessions.html", context)


@login_required
def courses_view(request):
    from apps.events.models import Registration

    rows = Registration.objects.filter(
        user=request.user, status__in=Registration.ACTIVE_STATUSES
    ).select_related("event", "order", "certificate")
    context = {"page_obj": _page(request, rows), "section": "courses"}
    return render(request, "accounts/courses.html", context)


@login_required
def downloads_view(request):
    from apps.shop.models import DownloadToken

    rows = DownloadToken.objects.filter(user=request.user).select_related("product")
    context = {"page_obj": _page(request, rows), "section": "downloads"}
    return render(request, "accounts/downloads.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def profile_view(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "مشخصات شما ذخیره شد.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"form": form, "section": "profile"})


def _template(request, step):
    # HTMX swaps only the card; a normal request gets the full page
    return f"accounts/includes/{step}.html" if request.htmx else "accounts/login.html"


def _panel_next(request):
    url = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(url, {request.get_host()}, request.is_secure()):
        return url
    return reverse("wagtailadmin_home")


@never_cache  # the backup codes are shown on this page
@login_required
@require_http_methods(["GET", "POST"])
def two_factor_view(request):
    """The panel's second step: set up the app once, then type its code each login."""
    if not two_factor.can_open_panel(request.user):
        return redirect("accounts:account")
    next_url = _panel_next(request)
    if request.user.is_verified():
        return redirect(next_url)
    form = TwoFactorForm(request.POST or None)
    context = {"form": form, "next": next_url}

    if two_factor.is_set_up(request.user):
        if form.is_valid():
            device = match_token(request.user, form.cleaned_data["code"])
            if device:
                otp_login(request, device)
                return redirect(next_url)
            form.add_error("code", "کد درست نیست یا منقضی شده است.")
        return render(request, "accounts/two_factor.html", {**context, "mode": "verify"})

    device = two_factor.pending_app_device(request.user)
    if form.is_valid():
        codes = two_factor.confirm_app(device, form.cleaned_data["code"])
        if codes:
            otp_login(request, device)
            context["codes"] = codes
            return render(request, "accounts/two_factor.html", {**context, "mode": "codes"})
        form.add_error("code", "کد درست نیست. ساعت گوشی را هم بررسی کنید.")
    context |= {
        "mode": "setup",
        "qr": two_factor.qr_code(device),
        "secret": two_factor.secret_for_typing(device),
    }
    return render(request, "accounts/two_factor.html", context)
