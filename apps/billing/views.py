from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from . import services
from .models import Invoice, ProForma


def _pdf_response(handle, filename):
    response = FileResponse(handle, content_type="application/pdf", filename=filename)
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
@require_GET
def invoice(request, number):
    row = get_object_or_404(Invoice.objects.select_related("order__user"), number=number)
    if row.order.user_id != request.user.pk and not request.user.has_perm("billing.view_invoice"):
        raise Http404  # the same answer as a number that does not exist
    return _pdf_response(services.invoice_pdf(row), f"invoice-{row.number}.pdf")


@login_required
@require_GET
def proforma(request, pk):
    row = get_object_or_404(ProForma.objects.select_related("order"), pk=pk, order__isnull=False)
    if row.order.user_id != request.user.pk and not request.user.has_perm("billing.view_proforma"):
        raise Http404
    response = HttpResponse(services.proforma_pdf(row), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="proforma-{row.pk}.pdf"'
    response["Cache-Control"] = "private, no-store"
    return response
