"""The panel additions from the second demo (REPORT #058, P1–P8)."""

import datetime as dt

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import EDITOR, FULL_ADMIN, SUPPORT, setup_roles
from apps.content.models import Comment
from apps.core.text import to_fa_digits
from apps.dashboard import stats
from apps.notifications.models import Notification
from apps.orders import services as orders
from apps.orders.models import Order
from apps.orders.services import OrderLine
from apps.shop.models import Coupon

pytestmark = pytest.mark.django_db


def staff(role, mobile="09120000001", **fields):
    setup_roles()
    user = get_user_model().objects.create_user(mobile, **fields)
    user.groups.add(Group.objects.get(name=role))
    return user


def test_greeting_names_the_person_and_their_role(client):
    client.force_login(staff(SUPPORT, first_name="نگار"))
    content = client.get(reverse("wagtailadmin_home")).content.decode()
    assert "سلام نگار" in content
    assert SUPPORT in content


def test_sales_chart_has_fourteen_days_and_only_for_sales(client):
    customer = get_user_model().objects.create_user("09121234567")
    order = orders.create_order(customer, [OrderLine(customer, "خدمت", 20_000_000)])
    with transaction.atomic():
        orders.mark_paid(order)
    days = stats.daily_sales(14)
    assert len(days) == 14
    assert days[-1]["total"] == 20_000_000 and days[-1]["height"] == 100

    client.force_login(staff(FULL_ADMIN))
    assert "فروش ۱۴ روز اخیر" in client.get(reverse("wagtailadmin_home")).content.decode()
    client.force_login(staff(SUPPORT, mobile="09120000002"))
    assert "فروش ۱۴ روز اخیر" not in client.get(reverse("wagtailadmin_home")).content.decode()


def test_old_sales_stay_off_the_chart():
    customer = get_user_model().objects.create_user("09121234567")
    order = orders.create_order(customer, [OrderLine(customer, "خدمت", 5_000_000)])
    with transaction.atomic():
        orders.mark_paid(order)
    Order.objects.filter(pk=order.pk).update(paid_at=timezone.now() - dt.timedelta(days=20))
    assert sum(day["total"] for day in stats.daily_sales(14)) == 0


def test_comment_is_approved_with_one_post_and_logged(client, article):
    comment = Comment.objects.create(page=article, name="خواننده", text="عالی", ip_hash="x")
    client.force_login(staff(EDITOR))
    listing = client.get(reverse("comments:index")).content.decode()
    assert reverse("comments:set_status", args=[comment.pk, "approve"]) in listing

    response = client.post(reverse("comments:set_status", args=[comment.pk, "approve"]))
    assert response.status_code == 302
    comment.refresh_from_db()
    assert comment.status == Comment.Status.APPROVED
    from wagtail.models import ModelLogEntry

    assert ModelLogEntry.objects.filter(action="hrweb.comment_approve").count() == 1


def test_comment_buttons_refuse_get_and_other_sites(client, article):
    comment = Comment.objects.create(page=article, name="خواننده", text="عالی", ip_hash="x")
    client.force_login(staff(EDITOR))
    url = reverse("comments:set_status", args=[comment.pk, "spam"])
    assert client.get(url).status_code == 405
    response = client.post(url, {"next": "https://evil.test/"})
    assert response["Location"] == reverse("comments:index")
    comment.refresh_from_db()
    assert comment.status == Comment.Status.SPAM


def test_support_cannot_moderate_comments(client, article):
    comment = Comment.objects.create(page=article, name="خواننده", text="عالی", ip_hash="x")
    client.force_login(staff(SUPPORT))
    client.post(reverse("comments:set_status", args=[comment.pk, "approve"]))
    comment.refresh_from_db()
    assert comment.status == Comment.Status.PENDING


def test_menu_shows_waiting_comments(rf, article):
    from types import SimpleNamespace

    from apps.dashboard.wagtail_hooks import add_menu_counts

    Comment.objects.create(page=article, name="خواننده", text="عالی", ip_hash="x")
    request = rf.get("/admin/")
    request.user = staff(EDITOR)
    registered = SimpleNamespace(name="comments", label="نظرهای مجله")
    items = [registered, SimpleNamespace(name="leads", label="سرنخ‌ها")]
    add_menu_counts(request, items)
    waiting = to_fa_digits(stats.pending_comments().count())
    assert items[0].label == f"نظرهای مجله ({waiting})"
    assert registered.label == "نظرهای مجله"  # the shared item is not changed
    assert items[1].label == "سرنخ‌ها"  # the editor may not see leads


def test_list_columns_for_coupons_orders_and_messages(client):
    Coupon.objects.create(
        code="AUTUMN", value=10, max_uses=5, valid_to=timezone.now() - dt.timedelta(days=1)
    )
    Notification.objects.create(channel="sms", to="09121234567", template="otp", body="کد ورود")
    customer = get_user_model().objects.create_user("09121234567")
    orders.create_order(customer, [OrderLine(customer, "کتاب نمونه", 1_000_000)])
    client.force_login(staff(FULL_ADMIN))
    coupons = client.get(reverse("panel_coupons:index")).content.decode()
    assert "۰ از ۵" in coupons and "منقضی" in coupons
    assert "کد ورود" in client.get(reverse("notifications:index")).content.decode()
    listing = client.get(reverse("panel_orders:index")).content.decode()
    assert "اقلام" in listing and "کتاب نمونه" in listing


def test_editor_sees_event_seats(client):
    client.force_login(staff(EDITOR))
    content = client.get(reverse("wagtailadmin_home")).content.decode()
    assert "رویدادهای پیش‌رو" in content
