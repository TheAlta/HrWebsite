import hashlib

from django.conf import settings


def client_ip(request) -> str:
    """Visitor IP. Behind Caddy (sprint 3) the first X-Forwarded-For hop is used,
    but only when TRUST_X_FORWARDED_FOR is on, so the header cannot be spoofed in dev."""
    if getattr(settings, "TRUST_X_FORWARDED_FOR", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def hashed_ip(request) -> str:
    """Salted SHA-256 of the visitor IP: usable for rate limits, not reversible to the IP."""
    raw = f"{settings.SECRET_KEY}:{client_ip(request)}".encode()
    return hashlib.sha256(raw).hexdigest()
