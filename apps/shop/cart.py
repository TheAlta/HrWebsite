"""The shopping cart, kept in the session so it survives logging in during checkout."""

from dataclasses import dataclass

from .models import Product

SESSION_KEY = "cart"
COUPON_KEY = "cart_coupon"
MAX_QTY = 10


@dataclass
class CartLine:
    product: Product
    qty: int

    @property
    def total(self):
        return self.product.price * self.qty


class Cart:
    def __init__(self, session):
        self.session = session

    @property
    def items(self) -> dict[str, int]:
        return self.session.get(SESSION_KEY, {})

    @property
    def count(self) -> int:
        return sum(self.items.values())

    @property
    def coupon_code(self) -> str:
        return self.session.get(COUPON_KEY, "")

    @coupon_code.setter
    def coupon_code(self, code: str):
        self.session[COUPON_KEY] = code

    def _save(self, items):
        self.session[SESSION_KEY] = items

    def set(self, product: Product, qty: int) -> None:
        """Set a quantity. A digital file is only ever bought once per order."""
        items = dict(self.items)
        qty = min(qty, 1 if product.is_digital else MAX_QTY)
        if qty > 0:
            items[str(product.pk)] = qty
        else:
            items.pop(str(product.pk), None)
        self._save(items)

    def add(self, product: Product) -> None:
        self.set(product, self.items.get(str(product.pk), 0) + 1)

    def clear(self) -> None:
        self._save({})
        self.session.pop(COUPON_KEY, None)

    def lines(self) -> list[CartLine]:
        """What can still be bought: products taken off sale drop out of the cart."""
        products = Product.objects.on_sale().filter(pk__in=[int(pk) for pk in self.items])
        return [CartLine(product, self.items[str(product.pk)]) for product in products]
