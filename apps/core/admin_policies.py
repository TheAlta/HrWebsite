from wagtail.permission_policies import ModelPermissionPolicy


class ReadOnlyPolicy(ModelPermissionPolicy):
    """For records only the system writes: messages, orders, payments."""

    def user_has_permission(self, user, action):
        if action in ("add", "change", "delete"):
            return False
        return super().user_has_permission(user, action)


class NoManualAddPolicy(ModelPermissionPolicy):
    """For records that only come from the site, such as leads."""

    def user_has_permission(self, user, action):
        if action == "add":
            return False
        return super().user_has_permission(user, action)


class EditOnlyPolicy(ModelPermissionPolicy):
    """For records the system creates and the owner only moves along their status.

    Deleting a row would skip what the status change does, such as freeing a seat.
    """

    def user_has_permission(self, user, action):
        if action in ("add", "delete"):
            return False
        return super().user_has_permission(user, action)
