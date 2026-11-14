"""The panel's home page (ADM-1) and the sales report (ADM-2).

Each block checks its own permission, so a support user never sees leads or sales.
"""

import copy
import datetime as dt

from django.db.models import Sum
from django.templatetags.static import static
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.admin.site_summary import SummaryItem
from wagtail.admin.ui.components import Component

from apps.accounts.roles import FULL_ADMIN
from apps.core import jalali
from apps.core.money import format_toman
from apps.core.text import to_fa_digits
from apps.orders.models import Order

from . import stats
from .views import SALES_PERMISSION, SalesReportView

SALES_DAYS = 30
CHART_DAYS = 14


class CountItem(SummaryItem):
    """One number on the panel's home page, linking to where it can be acted on."""

    template_name = "dashboard/summary_item.html"
    permission = ""
    icon = ""
    label = ""
    url_name = ""
    query = ""

    def is_shown(self):
        return self.request.user.has_perm(self.permission)

    def value(self):
        raise NotImplementedError

    def get_context_data(self, parent_context):
        url = reverse(self.url_name) + (f"?{self.query}" if self.query else "")
        return {"icon": self.icon, "value": self.value(), "label": self.label, "url": url}


class NewLeadsItem(CountItem):
    order = 10
    permission = "crm.view_lead"
    icon = "user"
    label = "سرنخ جدید"
    url_name = "leads:index"
    query = "status=new"

    def value(self):
        return stats.new_leads().count()


class SessionsItem(CountItem):
    order = 20
    permission = "booking.view_booking"
    icon = "date"
    label = "جلسه در ۷ روز آینده"
    url_name = "panel_bookings:index"

    def value(self):
        return stats.sessions_this_week().count()


class RegistrationsItem(CountItem):
    order = 25
    permission = "events.view_registration"
    icon = "group"
    label = "ثبت‌نام در رویدادهای پیش‌رو"
    url_name = "panel_registrations:index"

    def value(self):
        return stats.upcoming_registrations().count()


class ShipmentsItem(CountItem):
    order = 30
    permission = "shop.view_shipment"
    icon = "mail"
    label = "کتاب در انتظار ارسال"
    url_name = "panel_shipments:index"
    query = "status=preparing"

    def value(self):
        return stats.shipments_to_send().count()


class SalesItem(CountItem):
    order = 40
    permission = SALES_PERMISSION
    icon = "table"
    label = f"فروش {to_fa_digits(SALES_DAYS)} روز اخیر"
    url_name = "sales_report"

    def value(self):
        since = timezone.now() - dt.timedelta(days=SALES_DAYS)
        total = Order.objects.filter(status=Order.Status.PAID, paid_at__gte=since).aggregate(
            total=Sum("total")
        )["total"]
        return format_toman(total or 0)


class ListPanel(Component):
    template_name = ""
    permission = ""

    def __init__(self, request):
        self.request = request

    def rows(self):
        raise NotImplementedError

    def get_context_data(self, parent_context):
        return {"rows": self.rows(), "request": self.request}


class GreetingPanel(Component):
    """The first thing on the panel's home page: who is signed in, as what, and today's date."""

    name = "dashboard_greeting"
    order = 5
    template_name = "dashboard/panel_greeting.html"

    def __init__(self, request):
        self.request = request

    def get_context_data(self, parent_context):
        user = self.request.user
        if user.is_superuser:
            roles = [FULL_ADMIN]
        else:
            roles = list(user.groups.values_list("name", flat=True))
        return {
            "name": user.first_name or user.get_username(),
            "roles": "، ".join(roles),
            "today": to_fa_digits(jalali.format_date(timezone.localdate(), weekday=True)),
        }


class SalesChartPanel(Component):
    """Paid sales per day for the last two weeks, as bars (REPORT #058, P2)."""

    name = "dashboard_sales_chart"
    order = 45
    template_name = "dashboard/panel_sales_chart.html"
    permission = SALES_PERMISSION

    def __init__(self, request):
        self.request = request

    def get_context_data(self, parent_context):
        days = stats.daily_sales(CHART_DAYS)
        return {
            "days": days,
            "heading": f"فروش {to_fa_digits(CHART_DAYS)} روز اخیر",
            "total": format_toman(sum(day["total"] for day in days)),
        }


class SessionsPanel(ListPanel):
    name = "dashboard_sessions"
    order = 50
    template_name = "dashboard/panel_sessions.html"
    permission = "booking.view_booking"

    def rows(self):
        return stats.sessions_today_and_tomorrow()


class EventsPanel(ListPanel):
    """Seats and waiting lists only, so the content editor sees them too (P8)."""

    name = "dashboard_events"
    order = 60
    template_name = "dashboard/panel_events.html"
    permission = ("events.view_registration", "events.view_eventpage")

    def rows(self):
        return stats.upcoming_events()


class LeadsPanel(ListPanel):
    name = "dashboard_leads"
    order = 70
    template_name = "dashboard/panel_leads.html"
    permission = "crm.view_lead"

    def rows(self):
        return stats.new_leads().order_by("-created_at")[:5]


@hooks.register("insert_global_admin_css")
def panel_colours():
    """The panel in the site's colours, font and logo (REPORT #055)."""
    return format_html('<link rel="stylesheet" href="{}">', static("panel/panel.css"))


@hooks.register("construct_homepage_summary_items")
def add_summary_items(request, items):
    items.extend(
        item(request)
        for item in (NewLeadsItem, SessionsItem, RegistrationsItem, ShipmentsItem, SalesItem)
    )


def allowed(user, permission):
    """One permission, or any of a tuple of them."""
    names = permission if isinstance(permission, tuple) else (permission,)
    return any(user.has_perm(name) for name in names)


@hooks.register("construct_homepage_panels")
def add_panels(request, panels):
    panels.append(GreetingPanel(request))
    for panel_class in (SalesChartPanel, SessionsPanel, EventsPanel, LeadsPanel):
        if allowed(request.user, panel_class.permission):
            panels.append(panel_class(request))


# Menu items that show how many things wait for someone (P4): (menu name, permission, count)
MENU_COUNTS = (
    ("leads", "crm.view_lead", lambda: stats.new_leads().count()),
    ("comments", "content.view_comment", lambda: stats.pending_comments().count()),
)


@hooks.register("construct_main_menu")
def add_menu_counts(request, menu_items):
    """A copy of the item with the number in its label; the registered item stays as it was."""
    for index, item in enumerate(menu_items):
        for name, permission, count in MENU_COUNTS:
            if item.name == name and request.user.has_perm(permission):
                waiting = count()
                if waiting:
                    labelled = copy.copy(item)
                    labelled.label = f"{item.label} ({to_fa_digits(waiting)})"
                    menu_items[index] = labelled


class PermissionMenuItem(MenuItem):
    def __init__(self, *args, permission, **kwargs):
        super().__init__(*args, **kwargs)
        self.permission = permission

    def is_shown(self, request):
        return request.user.has_perm(self.permission)


@hooks.register("register_reports_menu_item")
def register_sales_report_menu_item():
    return PermissionMenuItem(
        "گزارش فروش",
        reverse("sales_report"),
        icon_name="table",
        order=50,
        permission=SALES_PERMISSION,
    )


@hooks.register("register_admin_urls")
def register_report_urls():
    return [path("reports/sales/", SalesReportView.as_view(), name="sales_report")]
