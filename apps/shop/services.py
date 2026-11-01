"""Selling books and files (SHOP-1..3, spec section 8.4).

Stock is taken when the order is placed, so two customers can never pay for the
last copy. An order left unpaid gives its stock back. A payment that arrives
after that takes the stock again, or tells the owner when none is left.
"""

from dataclasses import dataclass
from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.content.alerts import email_owner
from apps.content.models import SiteSettings
from apps.core.money import format_toman
from apps.notifications.services import send_sms
from apps.orders import services as orders
from apps.orders.models import Order
from apps.orders.services import OrderLine

from .cart import Cart, CartLine
from .models import Coupon, CouponUse, DownloadToken, Product, Shipment, normalize_code

ORDER_HOLD = timedelta(minutes=30)  # longer than a bank session
DOWNLOAD_DAYS = 7
DOWNLOAD_LIMIT = 5
COUPON_INVALID = "این کد تخفیف معتبر نیست."


class ShopError(Exception):
    """A user-facing reason the action was refused (message is Persian)."""


@dataclass
class Quote:
    lines: list[CartLine]
    subtotal: int
    discount: int
    shipping: int
    coupon: Coupon | None = None

    @property
    def total(self):
        return self.subtotal - self.discount + self.shipping

    @property
    def needs_shipping(self):
        return any(not line.product.is_digital for line in self.lines)


def _shipping_fee(lines: list[CartLine]) -> int:
    """One flat fee per order, from the panel. Free above the threshold if there is one."""
    if all(line.product.is_digital for line in lines):
        return 0
    site_settings = SiteSettings.for_default_site()
    if site_settings is None:
        return 0
    subtotal = sum(line.total for line in lines)
    threshold = site_settings.free_shipping_from
    return 0 if threshold and subtotal >= threshold else site_settings.shipping_fee


def _eligible_total(coupon: Coupon, lines: list[CartLine]) -> int:
    limited_to = set(coupon.products.values_list("pk", flat=True))
    return sum(line.total for line in lines if not limited_to or line.product.pk in limited_to)


def _discount(coupon: Coupon, lines: list[CartLine]) -> int:
    eligible = _eligible_total(coupon, lines)
    if coupon.type == Coupon.Type.PERCENT:
        return eligible * coupon.value // 100
    return min(coupon.value, eligible)


def _active_uses(coupon: Coupon):
    # A cancelled order gives its use back
    return coupon.uses.filter(order__status__in=[Order.Status.PENDING, Order.Status.PAID])


def check_coupon(coupon: Coupon, lines: list[CartLine], user=None, now=None) -> None:
    """Raise ShopError unless the code can be used on these lines right now."""
    now = now or timezone.now()
    if (
        not coupon.is_active
        or (coupon.valid_from and now < coupon.valid_from)
        or (coupon.valid_to and now > coupon.valid_to)
    ):
        raise ShopError(COUPON_INVALID)
    if coupon.max_uses is not None and _active_uses(coupon).count() >= coupon.max_uses:
        raise ShopError("ظرفیت استفاده از این کد تخفیف تمام شده است.")
    if (
        user is not None
        and coupon.per_user_limit is not None
        and _active_uses(coupon).filter(user=user).count() >= coupon.per_user_limit
    ):
        raise ShopError("شما قبلاً از این کد تخفیف استفاده کرده‌اید.")
    if not _eligible_total(coupon, lines):
        raise ShopError("این کد تخفیف روی محصولات سبد شما اعمال نمی‌شود.")


def find_coupon(code: str, *, lock=False) -> Coupon:
    rows = Coupon.objects.select_for_update() if lock else Coupon.objects
    coupon = rows.filter(code=normalize_code(code)).first()
    if coupon is None:
        raise ShopError(COUPON_INVALID)
    return coupon


def quote(lines: list[CartLine], coupon: Coupon | None = None) -> Quote:
    return Quote(
        lines=lines,
        subtotal=sum(line.total for line in lines),
        discount=_discount(coupon, lines) if coupon else 0,
        shipping=_shipping_fee(lines),
        coupon=coupon,
    )


def quote_cart(cart: Cart) -> tuple[Quote, str]:
    """The cart's prices, and why its saved code no longer applies, if it does not."""
    lines = cart.lines()
    if cart.coupon_code and lines:
        try:
            coupon = find_coupon(cart.coupon_code)
            check_coupon(coupon, lines)
        except ShopError as exc:
            return quote(lines), str(exc)
        return quote(lines, coupon), ""
    return quote(lines), ""


def place_order(user, cart: Cart, address: dict | None = None) -> Order:
    """Turn the cart into an order. Prices, stock and the code are checked again here.

    Products are locked in id order, so two carts with the same books cannot deadlock.
    """
    wanted = {int(pk): qty for pk, qty in cart.items.items()}
    with transaction.atomic():
        products = Product.objects.on_sale().filter(pk__in=wanted).order_by("pk")
        lines = [CartLine(product, wanted[product.pk]) for product in products.select_for_update()]
        if not lines:
            raise ShopError("سبد خرید شما خالی است.")
        if len(lines) != len(wanted):
            raise ShopError("یکی از محصولات سبد دیگر فروخته نمی‌شود. سبد را بررسی کنید.")
        for line in lines:
            if not line.product.is_digital and line.product.stock < line.qty:
                raise ShopError(f"موجودی «{line.product.title}» کافی نیست.")

        coupon = None
        if cart.coupon_code:
            coupon = find_coupon(cart.coupon_code, lock=True)
            check_coupon(coupon, lines, user)
        priced = quote(lines, coupon)
        if priced.needs_shipping and not address:
            raise ShopError("نشانی ارسال را وارد کنید.")

        for line in lines:
            if not line.product.is_digital:
                Product.objects.filter(pk=line.product.pk).update(stock=F("stock") - line.qty)
        order = orders.create_order(
            user,
            [
                OrderLine(line.product, line.product.title, line.product.price, line.qty)
                for line in lines
            ],
            discount=priced.discount,
            shipping=priced.shipping,
            coupon_code=coupon.code if coupon else "",
        )
        if coupon:
            CouponUse.objects.create(coupon=coupon, order=order, user=user)
        if priced.needs_shipping:
            Shipment.objects.create(order=order, **address)

    if order.total == 0:
        # Fully discounted: nothing to pay, so it goes straight to delivery
        with transaction.atomic():
            orders.mark_paid(order)
        orders.fulfil(order)
    cart.clear()
    return order


def _product_items(order: Order):
    content_type = ContentType.objects.get_for_model(Product)
    return order.items.filter(content_type=content_type)


def deliver_order(order: Order) -> None:
    """A paid order delivers what it bought (receiver of `order_paid`)."""
    items = list(_product_items(order))
    if not items:
        return
    products = {
        product.pk: product
        for product in Product.objects.filter(pk__in=[item.object_id for item in items])
    }
    expires_at = timezone.now() + timedelta(days=DOWNLOAD_DAYS)
    has_files = False
    for item in items:
        product = products[item.object_id]
        if product.is_digital:
            has_files = True
            DownloadToken.objects.create(
                user=order.user,
                product=product,
                order=order,
                expires_at=expires_at,
                downloads_left=DOWNLOAD_LIMIT,
            )
    if has_files:
        send_sms(order.user.mobile, "order_digital", {"token": order.number})

    shipment = Shipment.objects.filter(order=order).first()
    if shipment:
        _prepare_shipment(shipment, order)


def _prepare_shipment(shipment: Shipment, order: Order) -> None:
    if shipment.stock_released_at and not _take_stock_again(order):
        shipment.status = Shipment.Status.OUT_OF_STOCK
        shipment.save(update_fields=["status"])
        send_sms(order.user.mobile, "order_problem", {"token": order.number})
        email_owner(
            "پرداخت بدون موجودی",
            f"سفارش {order.number} بعد از پایان مهلت پرداخت شد و موجودی تمام شده است. "
            "کتاب تهیه یا مبلغ برگردانده شود.",
        )
        return
    shipment.status = Shipment.Status.PREPARING
    shipment.stock_released_at = None
    shipment.save(update_fields=["status", "stock_released_at"])
    email_owner(
        f"سفارش کتاب {order.number}",
        f"{shipment.recipient}، {shipment.city}. مبلغ: {format_toman(order.total)}.",
    )


def _physical_items(order: Order):
    ids = Product.objects.filter(kind=Product.Kind.PHYSICAL).values("pk")
    return _product_items(order).filter(object_id__in=ids).order_by("object_id")


def _take_stock_again(order: Order) -> bool:
    items = list(_physical_items(order))
    with transaction.atomic():
        products = Product.objects.select_for_update().filter(
            pk__in=[item.object_id for item in items]
        )
        stock = {product.pk: product.stock for product in products.order_by("pk")}
        if any(stock.get(item.object_id, 0) < item.qty for item in items):
            return False
        for item in items:
            Product.objects.filter(pk=item.object_id).update(stock=F("stock") - item.qty)
    return True


def release_unpaid(now=None) -> int:
    """Every 5 minutes: cancel shop orders left unpaid and give their stock back."""
    now = now or timezone.now()
    unpaid = Order.objects.filter(
        status=Order.Status.PENDING,
        created_at__lte=now - ORDER_HOLD,
        items__content_type=ContentType.objects.get_for_model(Product),
    ).distinct()
    released = 0
    for order in unpaid:
        with transaction.atomic():
            # Only one caller wins this, so stock can never come back twice
            if not orders.cancel_unpaid(order):
                continue
            Shipment.objects.filter(order=order).update(
                status=Shipment.Status.CANCELLED, stock_released_at=now
            )
            for item in _physical_items(order):
                Product.objects.filter(pk=item.object_id).update(stock=F("stock") + item.qty)
        released += 1
    return released


def notify_shipped(shipment: Shipment) -> None:
    send_sms(
        shipment.order.user.mobile,
        "order_shipped",
        {"token": shipment.order.number, "token2": shipment.tracking_code.replace(" ", "")},
    )


def consume_download(token: DownloadToken) -> bool:
    """Use up one download. The conditional update cannot go below zero under load."""
    updated = DownloadToken.objects.filter(
        pk=token.pk, downloads_left__gt=0, expires_at__gt=timezone.now()
    ).update(downloads_left=F("downloads_left") - 1)
    return bool(updated)
