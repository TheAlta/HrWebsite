"""Test helpers: an SMS provider that records messages instead of sending them."""

from .providers.base import SMSProvider, SMSResult


class CapturingSMS(SMSProvider):
    outbox: list[dict] = []

    def send_template(self, to, template, params):
        self.outbox.append({"to": to, "template": template, "params": dict(params)})
        return SMSResult(message_id=f"test-{len(self.outbox)}", raw={})
