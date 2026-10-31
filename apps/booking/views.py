import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.payments.views import begin_payment

from . import services
from .models import Booking, SessionType


def _session_type(type_id):
    return get_object_or_404(SessionType, pk=type_id, is_active=True)


def _parse_start(value):
    """Start time travels as a Unix timestamp, so it has no timezone ambiguity."""
    try:
        return dt.datetime.fromtimestamp(int(value), tz=dt.UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        raise Http404 from None


def slots(request, page, type_id):
    session_type = _session_type(type_id)
    return page.render(
        request,
        context_overrides={"session_type": session_type, "days": services.free_slots(session_type)},
        template="booking/slots.html",
    )


def confirm(request, page, type_id):
    """Review the chosen time; POST locks it and sends the customer to the bank."""
    session_type = _session_type(type_id)
    start_at = _parse_start(request.GET.get("start"))
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())

    if request.method == "POST":
        try:
            booking = services.hold_slot(request.user, session_type, start_at)
        except services.BookingError as exc:
            messages.error(request, str(exc))
            return redirect(page.url + page.reverse_subpage("slots", args=[session_type.pk]))
        if booking.order.total == 0:
            return redirect("orders:detail", number=booking.order.number)
        return begin_payment(request, booking.order)

    if not services.is_free(session_type, start_at):
        messages.error(request, services.SLOT_TAKEN)
        return redirect(page.url + page.reverse_subpage("slots", args=[session_type.pk]))
    return page.render(
        request,
        context_overrides={
            "session_type": session_type,
            "start_at": start_at,
            "hold_minutes": services.HOLD_MINUTES,
        },
        template="booking/confirm.html",
    )


def _own_booking(request, pk):
    return get_object_or_404(Booking, pk=pk, user=request.user)


@login_required
@require_POST
def cancel(request, pk):
    booking = _own_booking(request, pk)
    try:
        services.cancel(booking)
    except services.BookingError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "جلسه لغو شد.")
    return redirect("accounts:account")


@login_required
def reschedule(request, pk):
    booking = _own_booking(request, pk)
    if not services.can_change(booking):
        messages.error(request, "جابه‌جایی جلسه فقط تا ۲۴ ساعت قبل از شروع ممکن است.")
        return redirect("accounts:account")

    if request.method == "POST":
        try:
            services.reschedule(booking, _parse_start(request.POST.get("start")))
        except services.BookingError as exc:
            messages.error(request, str(exc))
            return redirect(reverse("booking:reschedule", args=[booking.pk]))
        messages.success(request, "زمان جلسه تغییر کرد.")
        return redirect("accounts:account")

    days = services.free_slots(booking.session_type, ignore=booking)
    return render(request, "booking/reschedule.html", {"booking": booking, "days": days})
