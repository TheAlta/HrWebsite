import threading
from datetime import timedelta

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, transaction
from django.urls import reverse
from django.utils import timezone
from wagtail.test.utils.form_data import rich_text

from apps.core import jalali
from apps.notifications.testing import CapturingSMS
from apps.orders import services as orders
from apps.orders.models import Order
from apps.shop import services
from apps.shop.cart import MAX_QTY, Cart
from apps.shop.models import Coupon, CouponUse, DownloadToken, Product, Shipment

pytestmark = pytest.mark.django_db


def make_cart(*products, code=""):
    session = SessionStore()
    cart = Cart(session)
    for product in products:
        cart.add(product)
    cart.coupon_code = code
    return cart


def pay(order):
    with transaction.atomic():
        orders.mark_paid(order)
    orders.fulfil(order)
    order.refresh_from_db()


def age(order, minutes=31):
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(minutes=minutes))


def stock(product):
    return Product.objects.get(pk=product.pk).stock


def last_sms(user):
    return [m for m in CapturingSMS.outbox if m["to"] == user.mobile][-1]


# --- cart -------------------------------------------------------------------------------


def test_cart_quantities_and_limits(book, ebook):
    cart = make_cart(book, book, ebook, ebook)
    assert cart.items == {str(book.pk): 2, str(ebook.pk): 1}
    cart.set(book, 999)
    assert cart.items[str(book.pk)] == MAX_QTY
    cart.set(book, 0)
    assert str(book.pk) not in cart.items


def test_product_off_sale_drops_out_of_the_cart(book, other_book):
    cart = make_cart(book, other_book)
    Product.objects.filter(pk=book.pk).update(is_active=False)
    assert [line.product for line in cart.lines()] == [other_book]


# --- coupons ----------------------------------------------------------------------------


def coupon(**fields):
    return Coupon.objects.create(code=fields.pop("code", "off10"), value=10, **fields)


def test_percent_discount(book):
    code = coupon()
    assert code.code == "OFF10"
    quote = services.quote(make_cart(book).lines(), code)
    assert quote.discount == 300_000


def test_amount_discount_never_exceeds_the_goods(book):
    code = Coupon.objects.create(code="BIG", type=Coupon.Type.AMOUNT, value=99_000_000)
    quote = services.quote(make_cart(book).lines(), code)
    assert quote.discount == 3_000_000
    assert quote.total == 0 + quote.shipping


def test_coupon_limited_to_a_product(book, other_book):
    code = coupon()
    code.products.add(other_book)
    lines = make_cart(book, other_book).lines()
    assert services.quote(lines, code).discount == 100_000
    with pytest.raises(services.ShopError):
        services.check_coupon(code, make_cart(book).lines())


def test_expired_and_future_and_inactive_coupons(book):
    lines = make_cart(book).lines()
    now = timezone.now()
    for fields in (
        {"code": "OLD", "valid_to": now - timedelta(days=1)},
        {"code": "SOON", "valid_from": now + timedelta(days=1)},
        {"code": "OFF", "is_active": False},
    ):
        with pytest.raises(services.ShopError):
            services.check_coupon(coupon(**fields), lines)


def test_coupon_code_is_found_in_any_case_and_digits(book):
    coupon(code="SALE۲۵")
    assert services.find_coupon(" sale25 ").code == "SALE25"


def test_per_user_limit(book, customer, address):
    Coupon.objects.create(code="ONCE", value=10, per_user_limit=1)
    pay(services.place_order(customer, make_cart(book, code="ONCE"), address))
    with pytest.raises(services.ShopError):
        services.place_order(customer, make_cart(book, code="ONCE"), address)


def test_max_uses_counts_every_customer(book, customer, other_customer, address):
    Coupon.objects.create(code="ONE", value=10, max_uses=1, per_user_limit=None)
    services.place_order(customer, make_cart(book, code="ONE"), address)
    with pytest.raises(services.ShopError):
        services.place_order(other_customer, make_cart(book, code="ONE"), address)


def test_cancelled_order_gives_the_use_back(book, customer, other_customer, address):
    Coupon.objects.create(code="ONE", value=10, max_uses=1)
    order = services.place_order(customer, make_cart(book, code="ONE"), address)
    age(order)
    services.release_unpaid()
    placed = services.place_order(other_customer, make_cart(book, code="ONE"), address)
    assert placed.discount == 300_000
    assert CouponUse.objects.count() == 2


def test_quote_reports_a_dead_code_instead_of_failing(book):
    quote, error = services.quote_cart(make_cart(book, code="NOPE"))
    assert quote.discount == 0
    assert error == services.COUPON_INVALID


def test_percent_over_100_is_refused(db):
    with pytest.raises(Exception, match="۱۰۰"):
        Coupon(code="X", value=101).clean()


# --- placing an order -------------------------------------------------------------------


def test_order_totals_with_discount_and_shipping(book, customer, address, shipping):
    Coupon.objects.create(code="OFF", value=10)
    order = services.place_order(customer, make_cart(book, code="OFF"), address)
    assert (order.subtotal, order.discount, order.shipping) == (3_000_000, 300_000, 500_000)
    assert order.total == 3_200_000
    assert order.coupon_code == "OFF"
    assert order.items.get().item == book


def test_free_shipping_above_the_threshold(book, customer, address, shipping):
    Product.objects.filter(pk=book.pk).update(price=20_000_000)
    assert services.place_order(customer, make_cart(book), address).shipping == 0


def test_digital_order_needs_no_address_or_shipping(ebook, customer, shipping):
    order = services.place_order(customer, make_cart(ebook))
    assert order.shipping == 0
    assert not Shipment.objects.exists()


def test_printed_book_needs_an_address(book, customer):
    with pytest.raises(services.ShopError):
        services.place_order(customer, make_cart(book))
    assert stock(book) == 2


def test_placing_takes_stock_and_saves_the_address(book, customer, address):
    order = services.place_order(customer, make_cart(book), address)
    assert stock(book) == 1
    assert order.shipment.city == "تهران"
    assert order.shipment.status == Shipment.Status.AWAITING_PAYMENT


def test_not_enough_stock_is_refused_and_nothing_changes(book, customer, address):
    cart = make_cart(book)
    cart.set(book, 3)
    with pytest.raises(services.ShopError):
        services.place_order(customer, cart, address)
    assert stock(book) == 2
    assert not Order.objects.exists()


def test_price_comes_from_the_database_not_the_cart(book, customer, address):
    cart = make_cart(book)
    Product.objects.filter(pk=book.pk).update(price=9_000_000)
    assert services.place_order(customer, cart, address).subtotal == 9_000_000


def test_product_removed_after_adding_stops_the_order(book, other_book, customer, address):
    cart = make_cart(book, other_book)
    Product.objects.filter(pk=book.pk).update(is_active=False)
    with pytest.raises(services.ShopError):
        services.place_order(customer, cart, address)


def test_placing_clears_the_cart(book, customer, address):
    cart = make_cart(book)
    services.place_order(customer, cart, address)
    assert cart.count == 0


def test_fully_discounted_order_is_delivered_at_once(ebook, customer):
    Coupon.objects.create(code="FREE", value=100)
    order = services.place_order(customer, make_cart(ebook, code="FREE"))
    order.refresh_from_db()
    assert (order.total, order.status) == (0, Order.Status.PAID)
    assert DownloadToken.objects.filter(order=order).exists()


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_two_customers_racing_for_the_last_copy(customer, other_customer, address):
    """Real parallel transactions: exactly one order goes through."""
    book = Product.objects.create(title="آخرین نسخه", slug="last", price=1_000, stock=1)
    barrier = threading.Barrier(2)
    won, lost = [], []

    def attempt(user):
        cart = make_cart(book)
        barrier.wait()
        try:
            won.append(services.place_order(user, cart, address))
        except services.ShopError:
            lost.append(user)
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt, args=[u]) for u in (customer, other_customer)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert (len(won), len(lost)) == (1, 1)
    assert stock(book) == 0


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_last_use_of_a_coupon_goes_to_one_customer(customer, other_customer):
    """The limit holds under parallel orders, with stock to spare."""
    ebook = Product.objects.create(
        title="فایل", slug="file", kind=Product.Kind.DIGITAL, price=1_000, file="products/x.pdf"
    )
    Coupon.objects.create(code="ONE", value=10, max_uses=1)
    barrier = threading.Barrier(2)
    won, lost = [], []

    def attempt(user):
        cart = make_cart(ebook, code="ONE")
        barrier.wait()
        try:
            won.append(services.place_order(user, cart))
        except services.ShopError:
            lost.append(user)
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt, args=[u]) for u in (customer, other_customer)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert (len(won), len(lost)) == (1, 1)


# --- unpaid orders ----------------------------------------------------------------------


def test_unpaid_order_gives_its_stock_back(book, customer, address):
    order = services.place_order(customer, make_cart(book), address)
    assert services.release_unpaid() == 0  # still within the hold
    age(order)
    assert services.release_unpaid() == 1
    assert services.release_unpaid() == 0  # stock cannot come back twice
    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    assert order.shipment.status == Shipment.Status.CANCELLED
    assert stock(book) == 2


def test_paid_order_is_never_released(book, customer, address):
    order = services.place_order(customer, make_cart(book), address)
    pay(order)
    age(order)
    assert services.release_unpaid() == 0
    assert stock(book) == 1


def test_orders_of_other_apps_are_left_alone(customer):
    from apps.orders.services import create_order

    order = create_order(customer, [])
    age(order)
    services.release_unpaid()
    order.refresh_from_db()
    assert order.status == Order.Status.PENDING


def test_late_payment_takes_the_stock_again(book, customer, address, shipping):
    order = services.place_order(customer, make_cart(book), address)
    age(order)
    services.release_unpaid()
    pay(order)
    assert order.shipment.status == Shipment.Status.PREPARING
    assert stock(book) == 1


def test_late_payment_without_stock_alerts_the_owner(book, customer, address, shipping):
    order = services.place_order(customer, make_cart(book), address)
    age(order)
    services.release_unpaid()
    Product.objects.filter(pk=book.pk).update(stock=0)
    pay(order)
    assert order.shipment.status == Shipment.Status.OUT_OF_STOCK
    assert stock(book) == 0
    assert last_sms(customer)["template"] == "order-problem"


# --- delivery ---------------------------------------------------------------------------


def test_paid_digital_order_gets_a_limited_link(ebook, customer):
    order = services.place_order(customer, make_cart(ebook))
    pay(order)
    token = DownloadToken.objects.get(order=order)
    assert token.downloads_left == 5
    assert 6 < (token.expires_at - timezone.now()).days + 1 <= 7
    assert last_sms(customer)["template"] == "order-digital"


def test_no_link_before_payment(ebook, customer):
    services.place_order(customer, make_cart(ebook))
    assert not DownloadToken.objects.exists()


def test_paid_book_is_prepared(book, customer, address, shipping):
    order = services.place_order(customer, make_cart(book), address)
    pay(order)
    assert order.shipment.status == Shipment.Status.PREPARING


def test_mixed_order_delivers_both(book, ebook, customer, address, shipping):
    order = services.place_order(customer, make_cart(book, ebook), address)
    pay(order)
    assert DownloadToken.objects.filter(order=order).count() == 1
    assert order.shipment.status == Shipment.Status.PREPARING


# --- downloads --------------------------------------------------------------------------


@pytest.fixture
def token(ebook, customer):
    order = services.place_order(customer, make_cart(ebook))
    pay(order)
    return DownloadToken.objects.get(order=order)


def body(response):
    return b"".join(response.streaming_content)


def test_buyer_downloads_the_file(client, token, customer):
    client.force_login(customer)
    response = client.get(token.get_absolute_url())
    assert response.status_code == 200
    assert body(response) == b"%PDF-1.4 secret"
    assert "attachment" in response["Content-Disposition"]
    assert response["Cache-Control"] == "private, no-store"
    token.refresh_from_db()
    assert token.downloads_left == 4


def test_link_needs_login(client, token):
    response = client.get(token.get_absolute_url())
    assert response.status_code == 302 and "/login" in response.url


def test_link_is_useless_to_another_customer(client, token, other_customer):
    client.force_login(other_customer)
    assert client.get(token.get_absolute_url()).status_code == 404
    token.refresh_from_db()
    assert token.downloads_left == 5


def test_used_up_link_stops_working(client, token, customer):
    DownloadToken.objects.filter(pk=token.pk).update(downloads_left=0)
    client.force_login(customer)
    assert client.get(token.get_absolute_url()).status_code == 410


def test_expired_link_stops_working(client, token, customer):
    DownloadToken.objects.filter(pk=token.pk).update(expires_at=timezone.now())
    client.force_login(customer)
    assert client.get(token.get_absolute_url()).status_code == 410


def test_missing_file_does_not_use_up_a_download(client, token, customer):
    token.product.file.delete(save=False)
    client.force_login(customer)
    assert client.get(token.get_absolute_url()).status_code == 404
    token.refresh_from_db()
    assert token.downloads_left == 5


def test_paid_file_has_no_public_address(client, settings, ebook):
    assert str(settings.MEDIA_ROOT) not in ebook.file.path
    assert client.get(f"/media/{ebook.file.name}").status_code == 404


def test_consume_cannot_go_below_zero(token):
    DownloadToken.objects.filter(pk=token.pk).update(downloads_left=1)
    assert services.consume_download(token) is True
    assert services.consume_download(token) is False


# --- pages ------------------------------------------------------------------------------


def test_shop_and_product_pages(client, shop_page, book):
    assert book.title in client.get(shop_page.url).content.decode()
    response = client.get(book.url)
    assert response.status_code == 200
    content = response.content.decode()
    assert '"@type": "Product"' in content
    assert f'href="http://testserver{book.url}"' in content


def test_persian_slug_reaches_the_product(client, shop_page):
    product = Product.objects.create(title="کتاب فارسی", price=1_000, stock=1)
    assert product.slug == "کتاب-فارسی"
    assert client.get(product.url).status_code == 200


def test_same_title_gets_a_new_slug(db):
    first = Product.objects.create(title="کتاب")
    second = Product.objects.create(title="کتاب")
    assert first.slug != second.slug


def test_product_off_sale_is_404(client, shop_page, book):
    url = book.url
    Product.objects.filter(pk=book.pk).update(is_active=False)
    assert client.get(url).status_code == 404


def test_sitemap_lists_products(client, shop_page, book):
    assert "/shop/book/" in client.get("/sitemap.xml").content.decode()


def test_add_to_cart_and_see_it(client, book):
    client.post(reverse("shop:cart_add", args=[book.pk]))
    assert book.title in client.get(reverse("shop:cart")).content.decode()


def test_out_of_stock_cannot_be_added(client, shop_page, book):
    Product.objects.filter(pk=book.pk).update(stock=0)
    client.post(reverse("shop:cart_add", args=[book.pk]))
    assert client.session.get("cart", {}) == {}


def test_htmx_update_returns_only_the_cart(client, book):
    client.post(reverse("shop:cart_add", args=[book.pk]))
    response = client.post(
        reverse("shop:cart_update", args=[book.pk]), {"qty": "2"}, headers={"HX-Request": "true"}
    )
    assert response.status_code == 200
    assert "<html" not in response.content.decode()
    assert client.session["cart"][str(book.pk)] == 2


def test_bad_quantity_removes_the_line(client, book):
    client.post(reverse("shop:cart_add", args=[book.pk]))
    client.post(reverse("shop:cart_update", args=[book.pk]), {"qty": "abc"})
    assert client.session["cart"] == {}


def test_coupon_applies_on_the_cart_page(client, book):
    Coupon.objects.create(code="OFF", value=10)
    client.post(reverse("shop:cart_add", args=[book.pk]))
    client.post(reverse("shop:cart_coupon"), {"code": "off"})
    response = client.get(reverse("shop:cart"))
    assert response.context["quote"].discount == 300_000


def test_wrong_coupon_shows_an_error(client, book):
    client.post(reverse("shop:cart_add", args=[book.pk]))
    client.post(reverse("shop:cart_coupon"), {"code": "nope"})
    assert services.COUPON_INVALID in client.get(reverse("shop:cart")).content.decode()


def test_checkout_needs_login_and_keeps_the_cart(client, book, customer):
    client.post(reverse("shop:cart_add", args=[book.pk]))
    response = client.get(reverse("shop:checkout"))
    assert response.status_code == 302 and "/login" in response.url
    client.force_login(customer)
    assert client.session["cart"] == {str(book.pk): 1}
    assert client.get(reverse("shop:checkout")).status_code == 200


def test_empty_checkout_goes_back_to_the_cart(client, customer):
    client.force_login(customer)
    assert client.get(reverse("shop:checkout")).url == reverse("shop:cart")


def test_checkout_sends_the_customer_to_the_bank(client, book, customer, address):
    client.force_login(customer)
    client.post(reverse("shop:cart_add", args=[book.pk]))
    response = client.post(reverse("shop:checkout"), address)
    assert response.status_code == 302 and "/payments/" in response.url
    assert Order.objects.get().shipment.recipient == address["recipient"]


def test_checkout_with_a_bad_postal_code_stays_on_the_form(client, book, customer, address):
    client.force_login(customer)
    client.post(reverse("shop:cart_add", args=[book.pk]))
    response = client.post(reverse("shop:checkout"), {**address, "postal_code": "12"})
    assert response.status_code == 200
    assert not Order.objects.exists()


def test_persian_digits_in_the_postal_code(client, book, customer, address):
    client.force_login(customer)
    client.post(reverse("shop:cart_add", args=[book.pk]))
    client.post(reverse("shop:checkout"), {**address, "postal_code": "۱۲۳۴۵۶۷۸۹۰"})
    assert Shipment.objects.get().postal_code == "1234567890"


def test_checkout_remembers_the_last_address(client, book, customer, address):
    services.place_order(customer, make_cart(book), address)
    client.force_login(customer)
    client.post(reverse("shop:cart_add", args=[book.pk]))
    response = client.get(reverse("shop:checkout"))
    assert response.context["form"].initial["city"] == "تهران"


def test_dead_coupon_never_reaches_the_bank(client, book, customer, address):
    client.force_login(customer)
    client.post(reverse("shop:cart_add", args=[book.pk]))
    client.post(reverse("shop:cart_coupon"), {"code": "nope"})
    response = client.post(reverse("shop:checkout"), address)
    assert response.url == reverse("shop:cart")
    assert not Order.objects.exists()


def test_order_page_shows_files_and_shipping(client, book, ebook, customer, address, shipping):
    order = services.place_order(customer, make_cart(book, ebook), address)
    pay(order)
    client.force_login(customer)
    content = client.get(reverse("orders:detail", args=[order.number])).content.decode()
    assert "دانلود" in content and "وضعیت ارسال" in content


def test_account_page_lists_files_and_orders(client, token, customer):
    client.force_login(customer)
    content = client.get(reverse("accounts:account")).content.decode()
    assert token.product.title in content
    assert token.get_absolute_url() in content


def test_header_shows_the_cart_only_when_it_has_items(client, shop_page, book):
    assert "سبد خرید،" not in client.get(shop_page.url).content.decode()
    client.post(reverse("shop:cart_add", args=[book.pk]))
    assert "سبد خرید،" in client.get(shop_page.url).content.decode()


# --- panel ------------------------------------------------------------------------------


def test_shipping_needs_a_tracking_code_and_sends_it(admin_client, book, customer, address):
    order = services.place_order(customer, make_cart(book), address)
    pay(order)
    url = reverse("panel_shipments:edit", args=[order.shipment.pk])
    assert admin_client.get(url).status_code == 200

    response = admin_client.post(url, {"status": "shipped", "tracking_code": ""})
    assert response.status_code == 200
    assert Shipment.objects.get().status == Shipment.Status.PREPARING

    response = admin_client.post(url, {"status": "shipped", "tracking_code": "TR 123"})
    assert response.status_code == 302
    assert Shipment.objects.get().status == Shipment.Status.SHIPPED
    sms = last_sms(customer)
    assert sms["template"] == "order-shipped"
    assert sms["params"]["token2"] == "TR123"


def test_shipment_status_cannot_jump_or_go_back(admin_client, book, customer, address):
    order = services.place_order(customer, make_cart(book), address)
    url = reverse("panel_shipments:edit", args=[order.shipment.pk])
    admin_client.post(url, {"status": "shipped", "tracking_code": "1"})
    assert Shipment.objects.get().status == Shipment.Status.AWAITING_PAYMENT


def test_saving_the_product_form_keeps_stock_sold_meanwhile(book, customer, address):
    from apps.shop.models import ProductAdminForm

    class Form(ProductAdminForm):
        class Meta:
            model = Product
            fields = ["title", "kind", "price", "stock"]

    form = Form(
        {"title": "نام تازه", "kind": "physical", "price": 3_000_000, "stock": 2}, instance=book
    )
    services.place_order(customer, make_cart(book), address)  # sold while the form is open
    assert form.is_valid()
    form.save()
    assert stock(book) == 1


def test_panel_creates_a_digital_product_with_a_private_file(admin_client, settings):
    upload = SimpleUploadedFile("book.pdf", b"%PDF-1.4 paid")
    data = {
        "title": "فایل تازه",
        "kind": "digital",
        "slug": "",
        "summary": "",
        "description": rich_text(""),
        "contents": rich_text(""),
        "price": "1000",
        "stock": "0",
        "sort_order": "0",
        "is_active": "on",
        "file": upload,
    }
    response = admin_client.post(reverse("panel_products:add"), data)
    assert response.status_code == 302
    product = Product.objects.get(title="فایل تازه")
    assert product.slug == "فایل-تازه"
    assert str(settings.MEDIA_ROOT) not in product.file.path

    data["file"] = ""  # saving again without a new file keeps the old one
    data["title"] = "فایل تازه ۲"
    url = reverse("panel_products:edit", args=[product.pk])
    assert admin_client.get(url).status_code == 200
    assert admin_client.post(url, data).status_code == 302
    product.refresh_from_db()
    assert product.title == "فایل تازه ۲" and product.file


def test_panel_creates_a_coupon_with_shamsi_dates(admin_client, book):
    data = {
        "code": "nowruz",
        "type": "percent",
        "value": "20",
        "per_user_limit": "1",
        "valid_from": "۱۴۰۵/۰۱/۰۱ ۰۰:۰۰",
        "valid_to": "1405/01/13 23:59",
        "products": [book.pk],
        "is_active": "on",
    }
    assert admin_client.post(reverse("panel_coupons:add"), data).status_code == 302
    coupon = Coupon.objects.get()
    assert coupon.code == "NOWRUZ"
    assert jalali.format_input(coupon.valid_to) == "۱۴۰۵/۰۱/۱۳ ۲۳:۵۹"
    assert list(coupon.products.all()) == [book]


def test_panel_pages_open(admin_client, book):
    for name in ("panel_products:index", "panel_products:add", "panel_coupons:index"):
        assert admin_client.get(reverse(name)).status_code == 200
    assert admin_client.get(reverse("panel_products:edit", args=[book.pk])).status_code == 200


def test_digital_product_needs_a_file(db):
    with pytest.raises(Exception, match="فایل"):
        Product(title="فایل", kind=Product.Kind.DIGITAL).clean()
