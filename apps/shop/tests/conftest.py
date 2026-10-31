import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.content.models import HomePage, SiteSettings
from apps.shop.models import Product, ShopPage


@pytest.fixture
def shop_page(db):
    page = ShopPage(title="فروشگاه", slug="shop")
    HomePage.objects.get().add_child(instance=page)
    return page


@pytest.fixture
def book(db):
    return Product.objects.create(title="کتاب نمونه", slug="book", price=3_000_000, stock=2)


@pytest.fixture
def other_book(db):
    return Product.objects.create(title="کتاب دوم", slug="book-2", price=1_000_000, stock=5)


@pytest.fixture
def ebook(db):
    product = Product(title="راهنمای نمونه", slug="ebook", kind=Product.Kind.DIGITAL, price=500_000)
    product.file.save("guide.pdf", SimpleUploadedFile("guide.pdf", b"%PDF-1.4 secret"))
    return product


@pytest.fixture
def customer(db):
    return get_user_model().objects.create_user("09121234567")


@pytest.fixture
def other_customer(db):
    return get_user_model().objects.create_user("09351112233")


@pytest.fixture
def admin_client(client, django_user_model):
    client.force_login(django_user_model.objects.create_superuser("09120000000", password="x"))
    return client


@pytest.fixture
def shipping(db):
    site_settings = SiteSettings.for_default_site()
    site_settings.shipping_fee = 500_000
    site_settings.free_shipping_from = 10_000_000
    site_settings.notify_email = "owner@example.com"
    site_settings.save()


ADDRESS = {
    "recipient": "علی رضایی",
    "mobile": "09121234567",
    "province": "تهران",
    "city": "تهران",
    "address": "خیابان نمونه، پلاک ۱",
    "postal_code": "1234567890",
}


@pytest.fixture
def address():
    return dict(ADDRESS)
