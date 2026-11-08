"""Login records in the panel (spec section 11): who logged in, from where, and who failed.

django-axes keeps the records; they are read-only here and trimmed after
LOGIN_LOG_DAYS. Only the full admin role sees them (it holds every permission).
"""

from axes.models import AccessFailureLog, AccessLog
from wagtail import hooks
from wagtail.admin.ui.tables import Column
from wagtail.admin.viewsets.model import ModelViewSet, ModelViewSetGroup
from wagtail.permissions import register_permission_policy

from apps.core import jalali
from apps.core.admin_policies import ReadOnlyPolicy


def _when(field, label):
    def value(row):
        moment = getattr(row, field)
        return jalali.format_datetime(moment) if moment else "—"

    return Column(field, label=label, accessor=value)


class LoginViewSet(ModelViewSet):
    model = AccessLog
    name = "panel_logins"
    url_prefix = "logins"
    icon = "user"
    menu_label = "ورودها"
    list_display = [
        Column("username", label="نام کاربری"),
        Column("ip_address", label="آدرس IP"),
        Column("path_info", label="از صفحه"),
        _when("attempt_time", "زمان ورود"),
        _when("logout_time", "زمان خروج"),
    ]
    search_fields = ["username", "ip_address"]
    ordering = ["-attempt_time"]
    form_fields = ["username"]  # required by ModelViewSet; editing is disabled by the policy
    copy_view_enabled = False


class FailedLoginViewSet(ModelViewSet):
    model = AccessFailureLog
    name = "panel_failed_logins"
    url_prefix = "failed-logins"
    icon = "warning"
    menu_label = "ورودهای ناموفق"
    list_display = [
        Column("username", label="نام کاربری"),
        Column("ip_address", label="آدرس IP"),
        Column("locked_out", label="قفل شد", accessor=lambda row: "بله" if row.locked_out else "—"),
        _when("attempt_time", "زمان"),
    ]
    search_fields = ["username", "ip_address"]
    ordering = ["-attempt_time"]
    form_fields = ["username"]  # required by ModelViewSet; editing is disabled by the policy
    copy_view_enabled = False


class SecurityGroup(ModelViewSetGroup):
    menu_label = "امنیت"
    menu_icon = "lock"
    menu_order = 900
    items = (LoginViewSet, FailedLoginViewSet)


register_permission_policy(AccessLog, ReadOnlyPolicy(AccessLog))
register_permission_policy(AccessFailureLog, ReadOnlyPolicy(AccessFailureLog))


@hooks.register("register_admin_viewset")
def register_security_group():
    return SecurityGroup()
