import datetime as dt
import io
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from apps.accounts.roles import EDITOR, FULL_ADMIN, SUPPORT, setup_roles
from apps.booking.models import Booking, SessionType
from apps.crm.models import Lead
from apps.dashboard import stats
from apps.orders import services as orders
from apps.orders.models import Order
from apps.orders.services import OrderLine

pytestmark = pytest.mark.django_db


@pytest.fixture
def customer(db):
    return get_user_model().objects.create_user("09121234567", first_name="=HYPERLINK(1)")


def staff_in(role, mobile="09120000001"):
    setup_roles()
    user = get_user_model().objects.create_user(mobile)
    user.groups.add(Group.objects.get(name=role))
    return user


def paid_order(user, total=10_000_000, when=None):
    order = orders.create_order(user, [OrderLine(user, "خدمت", total)])
    with transaction.atomic():
        orders.mark_paid(order)
    if when:
        Order.objects.filter(pk=order.pk).update(paid_at=when)
    order.refresh_from_db()
    return order


def lead(**fields):
    return Lead.objects.create(type="callback", name="سرنخ نمونه", ip_hash="x", **fields)


def book_today(user):
    session = SessionType.objects.create(title="جلسه امروز", mode="online", duration_min=60)
    start = timezone.now() + timedelta(hours=1)
    return Booking.objects.create(
        user=user,
        session_type=session,
        start_at=start,
        end_at=start + timedelta(hours=1),
        blocked_until=start + timedelta(hours=1),
        status=Booking.Status.CONFIRMED,
    )


# --- numbers ----------------------------------------------------------------------------


def test_sales_report_counts_refunds_separately(customer):
    now = timezone.now()
    first = paid_order(customer, 10_000_000, when=now - timedelta(days=2))
    paid_order(customer, 5_000_000, when=now - timedelta(days=1))
    paid_order(customer, 7_000_000, when=now - timedelta(days=60))  # outside the range
    orders.refund(first)
    report = stats.sales(now - timedelta(days=30), now + timedelta(minutes=1))
    assert (report.count, report.gross, report.refunded) == (2, 15_000_000, 10_000_000)
    assert report.net == 5_000_000
    assert [row[1] for row in report.periods] == [1, 1]
    assert report.by_kind == [("کاربران", 15_000_000)]


def test_long_ranges_are_grouped_by_month(customer):
    now = timezone.now()
    paid_order(customer, when=now - timedelta(days=100))
    paid_order(customer, when=now - timedelta(days=1))
    report = stats.sales(now - timedelta(days=365), now)
    assert len(report.periods) == 2
    assert all(" " in label for label, _, _ in report.periods)  # «آبان ۱۴۰۵»


def test_unpaid_orders_are_not_sales(customer):
    orders.create_order(customer, [OrderLine(customer, "خدمت", 1_000)])
    assert stats.sales(timezone.now() - timedelta(days=1), timezone.now()).count == 0


# --- report page ------------------------------------------------------------------------


@pytest.fixture
def admin_client(client):
    client.force_login(staff_in(FULL_ADMIN))
    return client


def test_report_with_shamsi_dates_includes_the_last_day(admin_client, customer):
    today = timezone.localdate()
    paid_order(customer, when=timezone.make_aware(dt.datetime.combine(today, dt.time(20, 0))))
    from apps.core import jalali

    day = jalali.format_input(timezone.make_aware(dt.datetime.combine(today, dt.time.min)))
    response = admin_client.get(reverse("sales_report"), {"start": day, "end": day})
    assert response.status_code == 200
    assert response.context["report"].count == 1


def test_report_refuses_a_reversed_range(admin_client):
    response = admin_client.get(
        reverse("sales_report"), {"start": "1405/08/10", "end": "1405/08/01"}
    )
    assert response.status_code == 200
    assert response.context["form"].errors


def test_excel_export_keeps_names_as_text(admin_client, customer):
    paid_order(customer)
    response = admin_client.get(reverse("sales_report"), {"export": "xlsx"})
    assert response["Content-Disposition"] == 'attachment; filename="sales.xlsx"'
    sheet = load_workbook(io.BytesIO(response.content)).active
    assert sheet.sheet_view.rightToLeft
    row = [cell.value for cell in sheet[2]]
    assert row[2].startswith("'=")  # never a live formula
    assert row[8] == 10_000_000


def test_report_needs_the_order_permission(client):
    client.force_login(staff_in(EDITOR))
    response = client.get(reverse("sales_report"))
    assert response.status_code in (302, 403)


# --- home page --------------------------------------------------------------------------


def test_full_admin_sees_every_block(admin_client, customer):
    lead()
    book_today(customer)
    paid_order(customer, 20_000_000)
    content = admin_client.get(reverse("wagtailadmin_home")).content.decode()
    for text in ("سرنخ جدید", "جلسه امروز", "فروش ۳۰ روز اخیر", "۲,۰۰۰,۰۰۰", "سرنخ نمونه"):
        assert text in content.replace("٬", ",")


def test_support_sees_sessions_but_never_leads_or_sales(client, customer):
    lead()
    book_today(customer)
    client.force_login(staff_in(SUPPORT))
    content = client.get(reverse("wagtailadmin_home")).content.decode()
    assert "جلسه امروز" in content
    assert "سرنخ نمونه" not in content
    assert "سرنخ جدید" not in content
    assert "فروش ۳۰ روز اخیر" not in content


# --- roles ------------------------------------------------------------------------------


def test_setup_roles_is_repeatable_and_keeps_manual_grants():
    setup_roles()
    support = Group.objects.get(name=SUPPORT)
    from django.contrib.auth.models import Permission

    extra = Permission.objects.get(codename="view_lead")
    support.permissions.add(extra)
    count = support.permissions.count()
    setup_roles()
    assert support.permissions.count() == count
    assert Group.objects.filter(name__in=[FULL_ADMIN, EDITOR, SUPPORT]).count() == 3


def test_support_cannot_open_leads_or_refund(client, customer):
    order = paid_order(customer)
    client.force_login(staff_in(SUPPORT))
    assert client.get(reverse("panel_bookings:index")).status_code == 200
    assert client.get(reverse("panel_shipments:index")).status_code == 200
    assert client.get(reverse("leads:index")).status_code == 302  # sent away: no permission
    client.post(reverse("panel_orders:refund", args=[order.pk]), {"reference": "x"})
    order.refresh_from_db()
    assert order.status == Order.Status.PAID


def test_editor_works_on_pages_but_not_sales(client):
    client.force_login(staff_in(EDITOR))
    assert client.get(reverse("wagtailadmin_explore_root")).status_code == 200
    assert client.get(reverse("wagtailimages:index")).status_code == 200
    assert client.get(reverse("panel_orders:index")).status_code == 302
    assert client.get(reverse("leads:index")).status_code == 302


def test_full_admin_can_refund(admin_client, customer):
    order = paid_order(customer)
    admin_client.post(reverse("panel_orders:refund", args=[order.pk]), {"reference": "x"})
    order.refresh_from_db()
    assert order.status == Order.Status.REFUNDED


def test_setup_roles_command(capsys):
    from django.core.management import call_command

    call_command("setup_roles")
    assert "مدیر کل" in capsys.readouterr().out
