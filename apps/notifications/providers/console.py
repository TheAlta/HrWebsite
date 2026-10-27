import logging
import uuid

from .base import SMSProvider, SMSResult

logger = logging.getLogger("sms")


class ConsoleSMS(SMSProvider):
    """Development provider: writes the message to the log instead of sending it.

    Read OTP codes with:  docker compose logs worker | grep SMS
    """

    def send_template(self, to, template, params):
        logger.warning("SMS to %s | template=%s | %s", to, template, params)
        return SMSResult(message_id=f"console-{uuid.uuid4().hex[:12]}", raw={"console": True})
