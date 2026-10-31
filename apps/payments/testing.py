"""Test helper: a gateway whose answers each test scripts."""

from .gateways.base import GatewayError, PaymentGateway, PaymentRequest, VerifyResult


class StubGateway(PaymentGateway):
    # Class attributes, because the service creates its own instance
    fail_request = False
    verify_error = False
    verify_ok = True
    verify_amount = None
    verify_calls: list[str] = []
    counter = 0

    @classmethod
    def reset(cls):
        cls.fail_request = cls.verify_error = False
        cls.verify_ok = True
        cls.verify_amount = None
        cls.verify_calls = []

    def request(self, amount, callback_url, description, *, mobile="", order_id=""):
        if self.fail_request:
            raise GatewayError("down")
        StubGateway.counter += 1
        authority = f"stub-{StubGateway.counter}"
        return PaymentRequest(authority=authority, redirect_url=f"https://bank.test/{authority}")

    def verify(self, authority, amount):
        self.verify_calls.append(authority)
        if self.verify_error:
            raise GatewayError("timeout")
        return VerifyResult(
            ok=self.verify_ok,
            ref_id="REF1",
            card_mask="6037****1234",
            amount=self.verify_amount,
            raw={"stub": True},
        )

    def authority_from_callback(self, params):
        return params.get("authority", "")


class BackupGateway(StubGateway):
    """Second gateway for fallback tests: never fails its request."""

    def request(self, amount, callback_url, description, *, mobile="", order_id=""):
        StubGateway.counter += 1
        authority = f"backup-{StubGateway.counter}"
        return PaymentRequest(authority=authority, redirect_url=f"https://backup.test/{authority}")
