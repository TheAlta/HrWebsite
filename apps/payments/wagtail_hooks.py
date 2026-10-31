from wagtail import hooks
from wagtail.admin.viewsets.model import ModelViewSet, ModelViewSetGroup
from wagtail.permissions import register_permission_policy

from apps.core.admin_policies import ReadOnlyPolicy
from apps.orders.models import Order

from .models import Payment


class OrderViewSet(ModelViewSet):
    model = Order
    name = "panel_orders"
    url_prefix = "orders"
    icon = "list-ul"
    menu_label = "سفارش‌ها"
    list_display = ["number", "user", "status", "total_display", "created_at"]
    list_filter = ["status"]
    search_fields = ["number", "user__mobile"]
    ordering = ["-created_at"]
    form_fields = ["status"]  # required by ModelViewSet; editing is disabled by the policy
    copy_view_enabled = False
    inspect_view_enabled = True


class PaymentViewSet(ModelViewSet):
    model = Payment
    name = "panel_payments"
    url_prefix = "payments"
    icon = "form"
    menu_label = "پرداخت‌ها"
    list_display = ["order", "gateway", "amount", "status", "ref_id", "created_at"]
    list_filter = ["status", "gateway"]
    search_fields = ["order__number", "ref_id", "authority"]
    ordering = ["-created_at"]
    form_fields = ["status"]  # required by ModelViewSet; editing is disabled by the policy
    copy_view_enabled = False
    inspect_view_enabled = True
    inspect_view_fields = [
        "order",
        "gateway",
        "amount",
        "status",
        "authority",
        "ref_id",
        "card_mask",
        "created_at",
        "verified_at",
    ]


class SalesGroup(ModelViewSetGroup):
    menu_label = "فروش"
    menu_icon = "list-ul"
    menu_order = 170
    items = (OrderViewSet, PaymentViewSet)


register_permission_policy(Order, ReadOnlyPolicy(Order))
register_permission_policy(Payment, ReadOnlyPolicy(Payment))


@hooks.register("register_admin_viewset")
def register_sales_group():
    return SalesGroup()
