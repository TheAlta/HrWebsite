from django.urls import path, reverse
from django.utils.functional import cached_property
from wagtail import hooks
from wagtail.admin.views.generic.models import InspectView
from wagtail.admin.viewsets.model import ModelViewSet
from wagtail.admin.widgets.button import Button, HeaderButton
from wagtail.permissions import register_permission_policy

from apps.core.admin_policies import EditOnlyPolicy
from apps.core.panel import ActionFormView
from apps.core.text import to_fa_digits
from apps.events.models import EventPage

from . import services
from .forms import IssueForm
from .models import Certificate

ISSUE_PERMISSION = "certificates.add_certificate"
REVOKE_PERMISSION = "certificates.change_certificate"


class CertificateInspectView(InspectView):
    @cached_property
    def header_buttons(self):
        certificate = self.object
        buttons = [
            HeaderButton(
                "دریافت PDF",
                url=reverse("certificates:download", args=[certificate.code]),
                icon_name="doc-full",
            )
        ]
        if certificate.is_valid and self.request.user.has_perm(REVOKE_PERMISSION):
            buttons.append(
                HeaderButton(
                    "ابطال گواهی",
                    url=reverse("panel_certificates:revoke", args=[certificate.pk]),
                    icon_name="cross",
                )
            )
        return buttons


class IssueView(ActionFormView):
    model = EventPage
    permission = ISSUE_PERMISSION
    page_title = "صدور گواهی حضور"
    log_action = "hrweb.issue_certificates"
    submit_label = "صدور گواهی"
    form_class = IssueForm
    error_class = services.CertificateError

    def get_page_title(self):
        return f"صدور گواهی حضور: {self.object.title}"

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "registrations": services.eligible(self.object)}

    @property
    def warning(self):
        if not services.eligible(self.object).exists():
            return "همه حاضران این رویداد گواهی دارند، یا ثبت‌نام قطعی‌ای ندارد."
        return "تیک کسانی را که حاضر نبودند بردارید. گواهی صادرشده فقط باطل می‌شود و حذف نمی‌شود."

    def get_success_url(self):
        return reverse("panel_certificates:index")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cancel_url"] = reverse("wagtailadmin_pages:edit", args=[self.object.pk])
        return context

    def perform(self, form):
        issued = services.issue(
            self.object, form.cleaned_data["registrations"], by=self.request.user
        )
        self.success_message = f"{to_fa_digits(len(issued))} گواهی صادر و پیامک شد."


class RevokeView(ActionFormView):
    model = Certificate
    permission = REVOKE_PERMISSION
    page_title = "ابطال گواهی"
    log_action = "hrweb.revoke_certificate"
    submit_label = "ابطال گواهی"
    warning = "صفحه استعلام از این به بعد «باطل شده» نشان می‌دهد. این کار برنمی‌گردد."
    success_message = "گواهی باطل شد."
    error_class = services.CertificateError

    def get_success_url(self):
        return reverse("panel_certificates:inspect", args=[self.object.pk])

    def perform(self, form):
        services.revoke(self.object)


class CertificateViewSet(ModelViewSet):
    model = Certificate
    name = "panel_certificates"
    url_prefix = "certificates"
    icon = "doc-full"
    menu_label = "گواهی‌های حضور"
    menu_order = 166
    add_to_admin_menu = True
    list_display = ["code", "name_display", "event_title", "status_display", "issued_display"]
    search_fields = ["code", "full_name", "event_title", "registration__user__mobile"]
    ordering = ["-issued_at"]
    copy_view_enabled = False
    inspect_view_enabled = True
    inspect_view_class = CertificateInspectView
    inspect_view_fields = [
        "code",
        "name_display",
        "event_title",
        "event_kind",
        "instructor",
        "event_start_display",
        "registration",
        "status_display",
        "issued_display",
        "issued_by",
        "revoked_display",
    ]

    def get_urlpatterns(self):
        return [
            *super().get_urlpatterns(),
            path("issue/<int:pk>/", IssueView.as_view(), name="issue"),
            path("<int:pk>/revoke/", RevokeView.as_view(), name="revoke"),
        ]


register_permission_policy(Certificate, EditOnlyPolicy(Certificate))


@hooks.register("register_admin_viewset")
def register_certificate_viewset():
    return CertificateViewSet()


def _issue_button(page, user):
    if page.specific_class is not EventPage or not user.has_perm(ISSUE_PERMISSION):
        return None
    if not services.can_issue(page.specific):
        return None
    url = reverse("panel_certificates:issue", args=[page.pk])
    return Button("صدور گواهی حضور", url, icon_name="doc-full", priority=70)


@hooks.register("register_page_header_buttons")
def page_header_buttons(page, user, view_name, next_url=None):
    button = _issue_button(page, user)
    if button:
        yield button


@hooks.register("register_page_listing_more_buttons")
def page_listing_more_buttons(page, user, next_url=None):
    button = _issue_button(page, user)
    if button:
        yield button
