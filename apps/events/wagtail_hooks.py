from wagtail import hooks
from wagtail.admin.viewsets.model import ModelViewSet
from wagtail.permissions import register_permission_policy

from apps.core.admin_policies import EditOnlyPolicy

from .models import Registration


class RegistrationViewSet(ModelViewSet):
    model = Registration
    name = "panel_registrations"
    url_prefix = "registrations"
    icon = "group"
    menu_label = "ثبت‌نام رویدادها"
    menu_order = 165
    add_to_admin_menu = True
    list_display = ["event", "user", "status", "order", "created_display"]
    list_filter = ["status", "event"]
    search_fields = ["user__mobile", "user__first_name", "user__last_name", "order__number"]
    ordering = ["-created_at"]
    list_export = ["event", "user", "status", "order", "created_display"]
    export_filename = "registrations"
    copy_view_enabled = False


register_permission_policy(Registration, EditOnlyPolicy(Registration))


@hooks.register("register_admin_viewset")
def register_registration_viewset():
    return RegistrationViewSet()
