"""Kavenegar adapter — the «verify/lookup» API for approved templates.

Docs: https://kavenegar.com/rest.html  (verify/lookup)
Template tokens: token, token2, token3 must not contain spaces; token10 and
token20 may (use them for names). Settings: KAVENEGAR_API_KEY.
"""

import httpx
from django.conf import settings

from .base import SMSError, SMSProvider, SMSResult

API_URL = "https://api.kavenegar.com/v1/{key}/verify/lookup.json"
ALLOWED_TOKENS = {"token", "token2", "token3", "token10", "token20"}
TIMEOUT_SECONDS = 10


class KavenegarSMS(SMSProvider):
    def __init__(self, api_key=None, client=None):
        self.api_key = api_key or settings.KAVENEGAR_API_KEY
        self.client = client or httpx.Client(timeout=TIMEOUT_SECONDS)

    def send_template(self, to, template, params):
        if not self.api_key:
            raise SMSError("KAVENEGAR_API_KEY is not set")
        unknown = set(params) - ALLOWED_TOKENS
        if unknown:
            raise SMSError(f"unsupported template tokens: {sorted(unknown)}")
        for name in ("token", "token2", "token3"):
            if " " in str(params.get(name, "")):
                raise SMSError(f"{name} must not contain spaces; use token10/token20")

        query = {"receptor": to, "template": template, **{k: str(v) for k, v in params.items()}}
        try:
            response = self.client.get(API_URL.format(key=self.api_key), params=query)
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SMSError(f"kavenegar unreachable: {exc}") from exc

        status = data.get("return", {}).get("status")
        if status != 200:
            message = data.get("return", {}).get("message", "")
            raise SMSError(f"kavenegar status {status}: {message}")
        entries = data.get("entries") or [{}]
        return SMSResult(message_id=str(entries[0].get("messageid", "")), raw=data)
