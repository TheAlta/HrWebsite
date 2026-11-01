from django.urls import path, reverse
from django.utils.functional import cached_property
from wagtail import hooks
from wagtail.admin.views.generic.models import InspectView
from wagtail.admin.viewsets.model import ModelViewSet, ModelViewSetGroup
from wagtail.admin.widgets.button import HeaderButton
from wagtail.permissions import register_permission_policy

from apps.accounts.models import Organization
from apps.core.admin_policies import NoDeletePolicy, ReadOnlyPolicy
from apps.core.panel import ActionFormView
from apps.orders.services import OrderError

from . import services
from .models import Invoice, ProForma


class InvoiceInspectView(InspectView):
    @cached_property
    def header_buttons(self):
        url = reverse("billing:invoice", args=[self.object.number])
        return [HeaderButton("دریافت PDF", url=url, icon_name="download")]


class InvoiceViewSet(ModelViewSet):
    model = Invoice
    name = "panel_invoices"
    url_prefix = "invoices"
    icon = "doc-full"
    menu_label = "فاکتورها"
    list_display = ["number", "order", "buyer_display", "total_display", "issued_display"]
    search_fields = ["number", "order__number", "order__user__mobile"]
    ordering = ["-number"]
    form_fields = ["voided_at"]  # required by ModelViewSet; editing is disabled by the policy
    copy_view_enabled = False
    inspect_view_enabled = True
    inspect_view_class = InvoiceInspectView
    inspect_view_fields = ["number", "order", "buyer_display", "issued_at", "voided_at"]
    list_export = ["number", "order", "buyer_display", "total_display", "issued_display"]
    export_filename = "invoices"


class ProFormaInspectView(InspectView):
    @cached_property
    def header_buttons(self):
        proforma = self.object
        buttons = []
        if self.request.user.has_perm("billing.change_proforma"):
            if proforma.status == ProForma.Status.DRAFT:
                url = reverse("panel_proformas:send", args=[proforma.pk])
                buttons.append(HeaderButton("ارسال برای مشتری", url=url, icon_name="mail"))
            if proforma.status in (ProForma.Status.DRAFT, ProForma.Status.SENT):
                url = reverse("panel_proformas:cancel", args=[proforma.pk])
                buttons.append(HeaderButton("لغو", url=url, icon_name="cross"))
        if proforma.order:
            url = reverse("panel_orders:inspect", args=[proforma.order_id])
            buttons.append(HeaderButton("سفارش و ثبت پرداخت", url=url, icon_name="list-ul"))
            url = reverse("billing:proforma", args=[proforma.pk])
            buttons.append(HeaderButton("دریافت PDF", url=url, icon_name="download"))
        return buttons


class ProFormaActionView(ActionFormView):
    model = ProForma
    permission = "billing.change_proforma"
    error_class = OrderError

    def get_success_url(self):
        return reverse("panel_proformas:inspect", args=[self.object.pk])


class SendProFormaView(ProFormaActionView):
    page_title = "ارسال پیش‌فاکتور"
    submit_label = "ارسال پیامک"
    warning = "سفارش ساخته و لینک پرداخت به موبایل رابط پیامک می‌شود. بعد از این، ویرایش ممکن نیست."
    success_message = "پیش‌فاکتور ارسال شد."

    def perform(self, form):
        services.send_proforma(self.object)


class CancelProFormaView(ProFormaActionView):
    page_title = "لغو پیش‌فاکتور"
    submit_label = "لغو پیش‌فاکتور"
    success_message = "پیش‌فاکتور لغو شد."

    def perform(self, form):
        services.cancel_proforma(self.object)


class ProFormaViewSet(ModelViewSet):
    model = ProForma
    name = "panel_proformas"
    url_prefix = "proformas"
    icon = "doc-empty"
    menu_label = "پیش‌فاکتورها"
    list_display = ["id", "organization", "mobile", "status", "total_display", "created_display"]
    list_filter = ["status"]
    search_fields = ["organization__name", "mobile", "contact_name"]
    ordering = ["-created_at"]
    copy_view_enabled = False
    inspect_view_enabled = True
    inspect_view_class = ProFormaInspectView
    inspect_view_fields = [
        "organization",
        "contact_name",
        "mobile",
        "status",
        "total_display",
        "valid_until",
        "note",
        "order",
    ]

    def get_urlpatterns(self):
        return [
            *super().get_urlpatterns(),
            path("<int:pk>/send/", SendProFormaView.as_view(), name="send"),
            path("<int:pk>/cancel/", CancelProFormaView.as_view(), name="cancel"),
        ]


class OrganizationViewSet(ModelViewSet):
    model = Organization
    name = "panel_organizations"
    url_prefix = "organizations"
    icon = "group"
    menu_label = "سازمان‌ها"
    list_display = ["name", "national_id", "economic_code"]
    search_fields = ["name", "national_id"]
    form_fields = ["name", "national_id", "economic_code", "address", "postal_code"]


class BillingGroup(ModelViewSetGroup):
    menu_label = "مالی"
    menu_icon = "doc-full"
    menu_order = 172
    items = (InvoiceViewSet, ProFormaViewSet, OrganizationViewSet)


register_permission_policy(Invoice, ReadOnlyPolicy(Invoice))
register_permission_policy(ProForma, NoDeletePolicy(ProForma))


@hooks.register("register_admin_viewset")
def register_billing_group():
    return BillingGroup()
