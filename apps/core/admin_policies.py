from wagtail.permission_policies import ModelPermissionPolicy


class ReadOnlyPolicy(ModelPermissionPolicy):
    """For records only the system writes: messages, orders, payments."""

    def user_has_permission(self, user, action):
        if action in ("add", "change", "delete"):
            return False
        return super().user_has_permission(user, action)
