from django.contrib import messages
from django.urls import path, reverse
from django.utils.functional import cached_property
from wagtail import hooks
from wagtail.admin.views.generic.models import InspectView
from wagtail.admin.viewsets.model import ModelViewSet, ModelViewSetGroup
from wagtail.admin.widgets.button import HeaderButton
from wagtail.permissions import register_permission_policy

from apps.core.admin_policies import NoManualAddPolicy
from apps.core.panel import ActionFormView
from apps.core.text import to_fa_digits

from . import services
from .models import Campaign, Subscriber


class CampaignInspectView(InspectView):
    @cached_property
    def header_buttons(self):
        campaign = self.object
        if campaign.status != Campaign.Status.DRAFT:
            return []
        if not self.request.user.has_perm("newsletter.change_campaign"):
            return []
        url = reverse("panel_campaigns:send", args=[campaign.pk])
        return [HeaderButton("ارسال", url=url, icon_name="mail")]


class SendCampaignView(ActionFormView):
    model = Campaign
    permission = "newsletter.change_campaign"
    page_title = "ارسال خبرنامه"
    log_action = "hrweb.send_campaign"
    submit_label = "ارسال"
    success_message = "ارسال شروع شد."

    def get_success_url(self):
        return reverse("panel_campaigns:inspect", args=[self.object.pk])

    @property
    def warning(self):
        count = services.audience(self.object.channel).count()
        note = " هر پیامک هزینه دارد." if self.object.channel == Campaign.Channel.SMS else ""
        return f"برای {to_fa_digits(count)} نفر ارسال می‌شود و قابل برگشت نیست.{note}"

    def perform(self, form):
        if not services.queue(self.object):
            messages.warning(self.request, "این خبرنامه قبلاً ارسال شده است.")


class CampaignViewSet(ModelViewSet):
    model = Campaign
    name = "panel_campaigns"
    url_prefix = "campaigns"
    icon = "mail"
    menu_label = "خبرنامه‌ها"
    list_display = ["title", "channel", "status", "sent_count", "created_display"]
    list_filter = ["channel", "status"]
    copy_view_enabled = False
    inspect_view_enabled = True
    inspect_view_class = CampaignInspectView
    inspect_view_fields = ["title", "channel", "body", "status", "sent_count", "sent_display"]

    def get_urlpatterns(self):
        return [
            *super().get_urlpatterns(),
            path("<int:pk>/send/", SendCampaignView.as_view(), name="send"),
        ]


class SubscriberViewSet(ModelViewSet):
    model = Subscriber
    name = "panel_subscribers"
    url_prefix = "subscribers"
    icon = "group"
    menu_label = "اعضای خبرنامه"
    list_display = ["__str__", "email_ok", "sms_ok", "source", "created_display"]
    list_filter = ["email_ok", "sms_ok", "source"]
    search_fields = ["email", "mobile"]
    list_export = ["email", "mobile", "email_ok", "sms_ok", "source", "created_display"]
    export_filename = "subscribers"
    copy_view_enabled = False


class NewsletterGroup(ModelViewSetGroup):
    menu_label = "خبرنامه"
    menu_icon = "mail"
    menu_order = 175
    items = (CampaignViewSet, SubscriberViewSet)


# Subscribers come only from people who agreed on the site
register_permission_policy(Subscriber, NoManualAddPolicy(Subscriber))


@hooks.register("register_admin_viewset")
def register_newsletter_group():
    return NewsletterGroup()
