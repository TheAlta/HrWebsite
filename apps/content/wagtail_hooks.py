from wagtail import hooks
from wagtail.admin.viewsets.model import ModelViewSet

from .models import Comment


class CommentViewSet(ModelViewSet):
    """Moderation queue for article comments (CMS-5)."""

    model = Comment
    icon = "comment"
    menu_label = "نظرهای مجله"
    menu_order = 210
    add_to_admin_menu = True
    list_display = ["name", "text", "page", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["name", "text"]
    form_fields = ["status", "name", "text"]
    ordering = ["-created_at"]
    inspect_view_enabled = True


@hooks.register("register_admin_viewset")
def register_comment_viewset():
    return CommentViewSet("comments")
