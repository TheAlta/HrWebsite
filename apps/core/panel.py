"""A panel page for one action on one record, such as a refund."""

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import FormView
from wagtail.admin.views.generic.base import WagtailAdminTemplateMixin
from wagtail.log_actions import log

# (action, label) of every panel action, for the panel's history (spec section 11)
LOG_ACTIONS: dict[str, str] = {}


class ActionFormView(WagtailAdminTemplateMixin, FormView):
    """Subclasses set the model and permission, and do the work in `perform`.

    `perform` raises `error_class` with a Persian message when the action is refused.
    A done action is written to the panel's history as `log_action`, labelled
    with the page title.
    """

    template_name = "panel/action_form.html"
    form_class = forms.Form
    header_icon = "cog"
    model = None
    permission = ""
    submit_label = ""
    warning = ""
    success_message = ""
    error_class = Exception
    log_action = ""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.log_action:
            LOG_ACTIONS[cls.log_action] = cls.page_title

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm(self.permission):
            raise PermissionDenied
        self.object = get_object_or_404(self.model, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_page_subtitle(self):
        return str(self.object)

    def get_breadcrumbs_items(self):
        return [
            *self.breadcrumbs_items,
            {"url": self.get_success_url(), "label": str(self.object)},
            {"url": "", "label": self.get_page_title()},
        ]

    def get_success_url(self):
        raise NotImplementedError

    def perform(self, form):
        raise NotImplementedError

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            submit_label=self.submit_label,
            warning=self.warning,
            cancel_url=self.get_success_url(),
        )
        return context

    def form_valid(self, form):
        try:
            self.perform(form)
        except self.error_class as exc:
            messages.error(self.request, str(exc))
        else:
            if self.log_action:
                log(instance=self.object, action=self.log_action, user=self.request.user)
            messages.success(self.request, self.success_message)
        return redirect(self.get_success_url())
