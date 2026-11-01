from wagtail import hooks
from wagtail.admin.viewsets.model import ModelViewSet, ModelViewSetGroup
from wagtail.permissions import register_permission_policy

from apps.core.admin_policies import EditOnlyPolicy

from .models import Coupon, Product, Shipment


class ProductViewSet(ModelViewSet):
    model = Product
    name = "panel_products"
    url_prefix = "products"
    icon = "doc-full"
    menu_label = "محصولات"
    list_display = ["title", "kind", "price_display", "stock", "is_active"]
    list_filter = ["kind", "is_active"]
    search_fields = ["title"]


class CouponViewSet(ModelViewSet):
    model = Coupon
    name = "panel_coupons"
    url_prefix = "coupons"
    icon = "tag"
    menu_label = "کدهای تخفیف"
    list_display = ["code", "type", "value", "max_uses", "is_active"]
    list_filter = ["type", "is_active"]
    search_fields = ["code"]


class ShipmentViewSet(ModelViewSet):
    model = Shipment
    name = "panel_shipments"
    url_prefix = "shipments"
    icon = "mail"
    menu_label = "ارسال‌ها"
    list_display = ["order", "recipient", "city", "status", "tracking_code", "created_display"]
    list_filter = ["status"]
    search_fields = ["order__number", "recipient", "mobile", "tracking_code"]
    ordering = ["-created_at"]
    copy_view_enabled = False


class ShopGroup(ModelViewSetGroup):
    menu_label = "فروشگاه"
    menu_icon = "tag"
    menu_order = 168
    items = (ProductViewSet, CouponViewSet, ShipmentViewSet)


register_permission_policy(Shipment, EditOnlyPolicy(Shipment))


@hooks.register("register_admin_viewset")
def register_shop_group():
    return ShopGroup()
