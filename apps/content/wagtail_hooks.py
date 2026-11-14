from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from wagtail import hooks
from wagtail.admin.ui.tables import Column
from wagtail.admin.viewsets.model import ModelViewSet
from wagtail.log_actions import log

from apps.core.panel import LOG_ACTIONS

from .models import Comment

# (status, log action, message) for the two one-click buttons on each comment row
COMMENT_ACTIONS = {
    "approve": (Comment.Status.APPROVED, "hrweb.comment_approve", "نظر تأیید و منتشر شد."),
    "spam": (Comment.Status.SPAM, "hrweb.comment_spam", "نظر رد شد."),
}
LOG_ACTIONS["hrweb.comment_approve"] = "تأیید نظر"
LOG_ACTIONS["hrweb.comment_spam"] = "رد نظر"


class CommentActionsColumn(Column):
    """Approve and reject buttons in the row itself (REPORT #058, P6): one click each."""

    cell_template_name = "panel/comment_actions_cell.html"

    def get_cell_context_data(self, instance, parent_context):
        context = super().get_cell_context_data(instance, parent_context)
        context["instance"] = instance
        context["csrf_token"] = parent_context.get("csrf_token")
        context["request"] = parent_context.get("request")
        return context


class CommentStatusView(View):
    """POST only: sets one comment's status and records it in the panel's history."""

    def post(self, request, pk, action):
        if not request.user.has_perm("content.change_comment") or action not in COMMENT_ACTIONS:
            raise PermissionDenied
        comment = get_object_or_404(Comment, pk=pk)
        status, log_action, message = COMMENT_ACTIONS[action]
        if comment.status != status:
            comment.status = status
            comment.save(update_fields=["status"])
            log(instance=comment, action=log_action, user=request.user)
        messages.success(request, message)
        back = request.POST.get("next", "")
        if not url_has_allowed_host_and_scheme(back, {request.get_host()}, request.is_secure()):
            back = reverse("comments:index")
        return redirect(back)


class CommentViewSet(ModelViewSet):
    """Moderation queue for article comments (CMS-5)."""

    model = Comment
    icon = "comment"
    menu_label = "نظرهای مجله"
    menu_order = 210
    add_to_admin_menu = True
    list_display = [
        "name",
        "text",
        "page",
        "status",
        "created_at",
        CommentActionsColumn("actions", label="بررسی", accessor="pk"),
    ]
    list_filter = ["status"]
    search_fields = ["name", "text"]
    form_fields = ["status", "name", "text"]
    ordering = ["-created_at"]
    inspect_view_enabled = True

    def get_urlpatterns(self):
        return [
            *super().get_urlpatterns(),
            path("<int:pk>/<str:action>/", CommentStatusView.as_view(), name="set_status"),
        ]


@hooks.register("register_admin_viewset")
def register_comment_viewset():
    return CommentViewSet("comments")
