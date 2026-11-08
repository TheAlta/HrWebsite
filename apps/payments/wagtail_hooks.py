from django import forms
from django.urls import path, reverse
from django.utils.functional import cached_property
from wagtail import hooks
from wagtail.admin.views.generic.models import InspectView
from wagtail.admin.viewsets.model import ModelViewSet, ModelViewSetGroup
from wagtail.admin.widgets.button import HeaderButton
from wagtail.permissions import register_permission_policy

from apps.core.admin_policies import ReadOnlyPolicy
from apps.core.panel import ActionFormView
from apps.orders import services as orders
from apps.orders.models import Order, Refund

from . import services
from .models import Payment

REFUND_PERMISSION = "orders.refund_order"


class OrderInspectView(InspectView):
    @cached_property
    def header_buttons(self):
        """What can still happen to this order, for those allowed to do it."""
        if not self.request.user.has_perm(REFUND_PERMISSION):
            return []
        order = self.object
        actions = []
        if order.status == Order.Status.PAID:
            actions.append(("ثبت بازگشت وجه", "refund", "undo"))
        if order.status == Order.Status.PENDING:
            if order.can_pay:
                actions.append(("ثبت پرداخت دستی", "manual_payment", "form"))
            actions.append(("لغو سفارش", "cancel", "cross"))
        return [
            HeaderButton(
                label, url=reverse(f"panel_orders:{name}", args=[order.pk]), icon_name=icon
            )
            for label, name, icon in actions
        ]


class OrderActionView(ActionFormView):
    model = Order
    permission = REFUND_PERMISSION
    error_class = orders.OrderError

    def get_success_url(self):
        return reverse("panel_orders:inspect", args=[self.object.pk])


class RefundForm(forms.Form):
    reference = forms.CharField(label="شماره پیگیری بازگشت وجه", required=False, max_length=100)
    note = forms.CharField(label="توضیح", required=False, widget=forms.Textarea(attrs={"rows": 3}))


class RefundView(OrderActionView):
    page_title = "ثبت بازگشت وجه"
    log_action = "hrweb.refund"
    submit_label = "ثبت بازگشت وجه"
    warning = (
        "این صفحه پول را برنمی‌گرداند. اول مبلغ را از پنل درگاه یا بانک برگردانید، بعد اینجا ثبت "
        "کنید. جلسه، صندلی و لینک دانلود این سفارش آزاد و فاکتور باطل می‌شود."
    )
    form_class = RefundForm
    success_message = "بازگشت وجه ثبت شد."

    def perform(self, form):
        orders.refund(self.object, by=self.request.user, **form.cleaned_data)


class CancelView(OrderActionView):
    page_title = "لغو سفارش"
    log_action = "hrweb.cancel_order"
    submit_label = "لغو سفارش"
    warning = "جلسه، صندلی یا موجودی نگه‌داشته‌شده برای این سفارش آزاد می‌شود."
    success_message = "سفارش لغو شد."

    def perform(self, form):
        orders.cancel_by_owner(self.object)


class ManualPaymentForm(forms.Form):
    method = forms.ChoiceField(
        label="نحوه پرداخت",
        choices=[("transfer", "حواله بانکی"), ("cheque", "چک"), ("cash", "نقدی")],
    )
    reference = forms.CharField(label="شماره حواله یا چک", required=False, max_length=100)


class ManualPaymentView(OrderActionView):
    page_title = "ثبت پرداخت دستی"
    log_action = "hrweb.manual_payment"
    submit_label = "ثبت پرداخت"
    warning = "بعد از ثبت، سفارش پرداخت‌شده حساب و تحویل و فاکتور انجام می‌شود."
    form_class = ManualPaymentForm
    success_message = "پرداخت ثبت شد."

    def perform(self, form):
        services.record_manual_payment(self.object, by=self.request.user, **form.cleaned_data)


class OrderViewSet(ModelViewSet):
    model = Order
    name = "panel_orders"
    url_prefix = "orders"
    icon = "list-ul"
    menu_label = "سفارش‌ها"
    list_display = ["number", "user", "status", "total_display", "created_display"]
    list_filter = ["status"]
    search_fields = ["number", "user__mobile"]
    ordering = ["-created_at"]
    form_fields = ["status"]  # required by ModelViewSet; editing is disabled by the policy
    copy_view_enabled = False
    inspect_view_enabled = True
    inspect_view_class = OrderInspectView
    inspect_view_fields = [
        "number",
        "user",
        "organization_display",
        "status",
        "items_display",
        "subtotal_display",
        "discount_display",
        "shipping_display",
        "total_display",
        "coupon_display",
        "paid_display",
        "created_display",
    ]
    list_export = ["number", "user", "status", "total", "discount", "shipping", "paid_at"]
    export_filename = "orders"

    def get_urlpatterns(self):
        return [
            *super().get_urlpatterns(),
            path("<int:pk>/refund/", RefundView.as_view(), name="refund"),
            path("<int:pk>/cancel/", CancelView.as_view(), name="cancel"),
            path("<int:pk>/manual-payment/", ManualPaymentView.as_view(), name="manual_payment"),
        ]


class PaymentViewSet(ModelViewSet):
    model = Payment
    name = "panel_payments"
    url_prefix = "payments"
    icon = "form"
    menu_label = "پرداخت‌ها"
    list_display = ["order", "gateway", "amount_display", "status", "ref_id", "created_display"]
    list_filter = ["status", "gateway"]
    search_fields = ["order__number", "ref_id", "authority"]
    ordering = ["-created_at"]
    form_fields = ["status"]  # required by ModelViewSet; editing is disabled by the policy
    copy_view_enabled = False
    inspect_view_enabled = True
    inspect_view_fields = [
        "order",
        "gateway",
        "amount_display",
        "status",
        "authority",
        "ref_id",
        "card_mask",
        "created_display",
        "verified_display",
    ]


class RefundViewSet(ModelViewSet):
    model = Refund
    name = "panel_refunds"
    url_prefix = "refunds"
    icon = "undo"
    menu_label = "بازگشت وجه‌ها"
    list_display = ["order", "amount_display", "reference", "created_by", "created_display"]
    search_fields = ["order__number", "reference"]
    form_fields = ["reference"]  # required by ModelViewSet; editing is disabled by the policy
    copy_view_enabled = False
    inspect_view_enabled = True
    inspect_view_fields = [
        "order",
        "amount_display",
        "reference",
        "note",
        "created_by",
        "created_display",
    ]


class SalesGroup(ModelViewSetGroup):
    menu_label = "فروش"
    menu_icon = "list-ul"
    menu_order = 170
    items = (OrderViewSet, PaymentViewSet, RefundViewSet)


register_permission_policy(Order, ReadOnlyPolicy(Order))
register_permission_policy(Payment, ReadOnlyPolicy(Payment))
register_permission_policy(Refund, ReadOnlyPolicy(Refund))


@hooks.register("register_admin_viewset")
def register_sales_group():
    return SalesGroup()
