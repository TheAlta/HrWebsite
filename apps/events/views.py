from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.payments.views import begin_payment

from . import services
from .models import Registration


@require_POST
def register(request, page):
    if not request.user.is_authenticated:
        return redirect_to_login(page.url)
    try:
        registration = services.register(request.user, page)
    except services.RegistrationError as exc:
        messages.error(request, str(exc))
        return redirect(page.url)

    if registration.status == Registration.Status.PENDING:
        return begin_payment(request, registration.order)
    if registration.status == Registration.Status.WAITLIST:
        messages.info(request, "ظرفیت پر است و در لیست انتظار قرار گرفتید.")
    else:
        messages.success(request, "ثبت‌نام شما انجام شد.")
    return redirect(page.url)


@login_required
@require_POST
def cancel(request, pk):
    registration = get_object_or_404(Registration, pk=pk, user=request.user)
    try:
        services.cancel(registration)
    except services.RegistrationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "ثبت‌نام لغو شد.")
    return redirect("accounts:account")
