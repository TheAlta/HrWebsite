from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.core.http import hashed_ip

from . import services
from .forms import FORMS
from .models import ConsultationPage, LeadType

RATE_LIMIT_MESSAGE = "تعداد درخواست‌های شما زیاد است. لطفاً چند دقیقه دیگر تلاش کنید."


@require_POST
def submit(request, kind):
    """One endpoint for every lead form. HTMX swaps the form for a thank-you
    message; without JavaScript the visitor lands on a full page."""
    try:
        form_class = FORMS[LeadType(kind)]
    except ValueError:
        raise Http404 from None
    form = form_class(request.POST)
    template = f"crm/includes/{kind}_form.html"

    if form.is_bot:
        return _thanks(request, kind, form=None)  # pretend success, save nothing
    if not form.is_valid():
        return _render(request, template, kind, {"form": form}, status=200)
    try:
        lead = services.create_lead(form, request, hashed_ip(request))
    except services.LeadRateLimited:
        return _render(
            request, template, kind, {"form": form, "error": RATE_LIMIT_MESSAGE}, status=429
        )
    return _thanks(request, kind, form=form, lead=lead)


def _thanks(request, kind, form, lead=None):
    context = {"kind": kind}
    if kind == LeadType.DOWNLOAD and form is not None:
        context["document"] = form.document_obj
    if kind == LeadType.CONSULTATION:
        page = ConsultationPage.objects.live().first()
        context["thank_you_text"] = page.thank_you_text if page else None
    if request.htmx:
        return render(request, "crm/includes/thanks.html", context)
    if kind == LeadType.DOWNLOAD and form is not None:
        return redirect(form.document_obj.url)
    return render(request, "crm/thanks.html", context)


def _render(request, template, kind, context, status):
    if request.htmx:
        return render(request, template, context, status=status)
    # No JavaScript: show the form with its errors on its own page
    if kind == LeadType.CONSULTATION:
        page = ConsultationPage.objects.live().first()
        if page:
            return page.serve(request, form=context["form"])
    return render(
        request, "crm/form_page.html", {**context, "form_template": template}, status=status
    )
