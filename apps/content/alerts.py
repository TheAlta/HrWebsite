import logging

from apps.notifications.services import send_email

from .models import SiteSettings

logger = logging.getLogger(__name__)


def email_owner(subject: str, message: str) -> None:
    """Tell the owner something needs a person, such as a manual refund."""
    site_settings = SiteSettings.for_default_site()
    if site_settings and site_settings.notify_email:
        send_email(
            site_settings.notify_email,
            subject,
            "notifications/email/owner_alert.txt",
            {"message": message},
        )
    else:
        logger.error("owner alert not delivered: %s: %s", subject, message)
