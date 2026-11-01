from wagtail import hooks
from wagtail.admin.views.generic.models import IndexView
from wagtail.admin.viewsets.model import ModelViewSet
from wagtail.permissions import register_permission_policy

from apps.core.admin_policies import NoManualAddPolicy

from .models import Lead

EXPORT_HEADINGS = {
    "created_at": "زمان ثبت",
    "type": "نوع",
    "status": "وضعیت",
    "name": "نام",
    "mobile": "موبایل",
    "email": "ایمیل",
    "company": "سازمان",
    "payload": "جزئیات",
    "source_url": "صفحه ارسال",
    "utm": "کمپین",
    "marketing_consent": "رضایت تبلیغات",
}


class LeadIndexView(IndexView):
    export_headings = EXPORT_HEADINGS


class LeadViewSet(ModelViewSet):
    """Simple CRM in the panel (LEAD-5): status, notes, reminders, Excel export.

    Lead data is confidential (spec section 11): only users with the lead
    permissions (superusers by default) see this menu.
    """

    model = Lead
    icon = "user"
    menu_label = "سرنخ‌ها"
    menu_order = 150
    add_to_admin_menu = True
    list_display = ["name", "type", "status", "mobile", "company", "created_at"]
    list_filter = ["status", "type", "created_at"]
    search_fields = ["name", "mobile", "email", "company"]
    ordering = ["-created_at"]
    inspect_view_enabled = True
    list_export = list(EXPORT_HEADINGS)
    export_filename = "leads"
    index_view_class = LeadIndexView
    copy_view_enabled = False


register_permission_policy(Lead, NoManualAddPolicy(Lead))


@hooks.register("register_admin_viewset")
def register_lead_viewset():
    return LeadViewSet("leads")
