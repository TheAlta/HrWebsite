import datetime as dt
import io

from django import forms
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import HttpResponse
from django.utils import timezone
from django.views.generic import TemplateView
from openpyxl import Workbook
from wagtail.admin.views.generic.base import WagtailAdminTemplateMixin

from apps.core import jalali
from apps.core.widgets import JalaliDateTimeInput

from . import stats

DEFAULT_DAYS = 30
# Sales figures are for the owner; support staff see orders but not totals
SALES_PERMISSION = "orders.view_sales"
FORMULA_START = ("=", "+", "-", "@")


class RangeForm(forms.Form):
    start = forms.DateTimeField(label="از", required=False, widget=JalaliDateTimeInput)
    end = forms.DateTimeField(label="تا", required=False, widget=JalaliDateTimeInput)

    def clean(self):
        data = super().clean()
        end = data.get("end")
        if end and end.time() == dt.time.min:
            # «تا ۳۰ آبان» means to the end of that day, not its first minute
            data["end"] = end + dt.timedelta(days=1)
        if data.get("start") and data.get("end") and data["start"] >= data["end"]:
            raise forms.ValidationError("«تا» باید بعد از «از» باشد.")
        return data


def _range(form):
    """The chosen range, or the last 30 days up to the end of today."""
    _, end = stats.day_bounds(timezone.localdate())
    start = end - dt.timedelta(days=DEFAULT_DAYS)
    if form.is_valid():
        start = form.cleaned_data["start"] or start
        end = form.cleaned_data["end"] or end
    return start, end


def _cell(value):
    # A customer's name starting with "=" must stay text, never become a formula
    if isinstance(value, str) and value.startswith(FORMULA_START):
        return "'" + value
    return value


class SalesReportView(PermissionRequiredMixin, WagtailAdminTemplateMixin, TemplateView):
    """Sales by period and by kind, with an Excel file of the orders (ADM-2)."""

    permission_required = SALES_PERMISSION
    template_name = "dashboard/sales_report.html"
    page_title = "گزارش فروش"
    header_icon = "table"

    def get_breadcrumbs_items(self):
        return [*self.breadcrumbs_items, {"url": "", "label": self.page_title}]

    def get(self, request, *args, **kwargs):
        self.form = RangeForm(request.GET or None)
        self.report = stats.sales(*_range(self.form))
        if request.GET.get("export") == "xlsx":
            return self.excel()
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(form=self.form, report=self.report)
        return context

    def excel(self):
        book = Workbook()
        sheet = book.active
        sheet.title = "فروش"
        sheet.sheet_view.rightToLeft = True
        sheet.append(
            [
                "شماره سفارش",
                "تاریخ پرداخت",
                "مشتری",
                "موبایل",
                "اقلام",
                "جمع (ریال)",
                "تخفیف (ریال)",
                "ارسال (ریال)",
                "مبلغ نهایی (ریال)",
                "وضعیت",
            ]
        )
        for order in self.report.orders:
            sheet.append(
                [
                    _cell(value)
                    for value in (
                        order.number,
                        jalali.format_datetime(order.paid_at),
                        order.user.get_full_name(),
                        order.user.mobile,
                        order.items_display(),
                        order.subtotal,
                        order.discount,
                        order.shipping,
                        order.total,
                        order.get_status_display(),
                    )
                ]
            )
        buffer = io.BytesIO()
        book.save(buffer)
        response = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="sales.xlsx"'
        return response
