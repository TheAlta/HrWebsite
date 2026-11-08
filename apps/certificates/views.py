from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from . import services
from .forms import VerifyForm
from .models import Certificate


@require_GET
def verify(request, code=""):
    """Public check of a code, typed in the form or opened from the QR on the PDF."""
    value = code or request.GET.get("code", "")
    form = VerifyForm({"code": value}) if value else VerifyForm()
    certificate = None
    if form.is_bound and form.is_valid():
        certificate = services.lookup(form.cleaned_data["code"])
    context = {"form": form, "certificate": certificate, "searched": form.is_bound}
    response = render(request, "certificates/verify.html", context)
    response["X-Robots-Tag"] = "noindex"
    return response


@login_required
@require_GET
def download(request, code):
    certificate = get_object_or_404(
        Certificate.objects.select_related("registration__user"), code=code
    )
    is_owner = certificate.registration.user_id == request.user.pk
    if not is_owner and not request.user.has_perm("certificates.view_certificate"):
        raise Http404  # the same answer as a code that does not exist
    if is_owner and not certificate.is_valid:
        raise Http404
    if not services.fill_name(certificate):
        if not is_owner:
            messages.error(request, "نامی برای این گواهی ثبت نشده است.")
            return redirect("panel_certificates:edit", certificate.pk)
        messages.info(request, "برای دریافت گواهی، اول نام و نام خانوادگی خود را وارد کنید.")
        return redirect("accounts:profile")
    response = HttpResponse(services.certificate_pdf(certificate), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="certificate-{certificate.code}.pdf"'
    response["Cache-Control"] = "private, no-store"
    return response
