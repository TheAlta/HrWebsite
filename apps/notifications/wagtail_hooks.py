from wagtail import hooks
from wagtail.admin.viewsets.model import ModelViewSet
from wagtail.permission_policies import ModelPermissionPolicy
from wagtail.permissions import register_permission_policy

from .models import Notification


class ReadOnlyPolicy(ModelPermissionPolicy):
    """The log is written by the system only."""

    def user_has_permission(self, user, action):
        if action in ("add", "change", "delete"):
            return False
        return super().user_has_permission(user, action)


class NotificationViewSet(ModelViewSet):
    model = Notification
    icon = "mail"
    menu_label = "پیام‌های ارسالی"
    menu_order = 900
    add_to_admin_menu = True
    list_display = ["to", "channel", "template", "status", "created_at"]
    list_filter = ["channel", "status"]
    search_fields = ["to", "template"]
    ordering = ["-created_at"]
    inspect_view_enabled = True
    inspect_view_fields = [
        "channel",
        "to",
        "template",
        "params",
        "body",
        "status",
        "error",
        "attempts",
        "provider_message_id",
        "created_at",
        "sent_at",
    ]
    form_fields = ["status"]  # required by ModelViewSet; editing is disabled by the policy


register_permission_policy(Notification, ReadOnlyPolicy(Notification))


@hooks.register("register_admin_viewset")
def register_notification_viewset():
    return NotificationViewSet("notifications")
