"""Comment submission service (CMS-5).

Anti-spam without captcha (REPORT #023): honeypot field, per-visitor rate
limit, and every comment waits for admin approval before it is shown.
"""

from datetime import timedelta

from django.contrib import messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.utils import timezone

from apps.core.http import hashed_ip

from .forms import CommentForm
from .models import Comment

RATE_LIMIT_COUNT = 3
RATE_LIMIT_WINDOW = timedelta(minutes=10)

SUCCESS_MESSAGE = "نظر شما ثبت شد و پس از تأیید نمایش داده می‌شود."
RATE_LIMIT_MESSAGE = "تعداد نظرهای شما زیاد است. لطفاً چند دقیقه دیگر دوباره تلاش کنید."


def is_rate_limited(ip_hash: str) -> bool:
    since = timezone.now() - RATE_LIMIT_WINDOW
    return (
        Comment.objects.filter(ip_hash=ip_hash, created_at__gte=since).count() >= RATE_LIMIT_COUNT
    )


def handle_submission(page, request):
    form = CommentForm(request.POST)
    ip_hash = hashed_ip(request)

    if form.is_bot:
        # Pretend success so the bot learns nothing
        return _respond(page, request, CommentForm(), SUCCESS_MESSAGE, ok=True)

    if not form.is_valid():
        return _respond(page, request, form, None, ok=False)

    if is_rate_limited(ip_hash):
        return _respond(page, request, form, RATE_LIMIT_MESSAGE, ok=False)

    Comment.objects.create(
        page=page,
        name=form.cleaned_data["name"],
        email=form.cleaned_data["email"],
        text=form.cleaned_data["text"],
        ip_hash=ip_hash,
    )
    return _respond(page, request, CommentForm(), SUCCESS_MESSAGE, ok=True)


def _respond(page, request, form, message, *, ok):
    if getattr(request, "htmx", False):
        return TemplateResponse(
            request,
            "content/includes/comment_form.html",
            {"page": page, "comment_form": form, "message": message, "ok": ok},
            status=200 if ok or not message else 429,
        )
    # Without JavaScript: full page round trip
    if ok:
        messages.success(request, message)
        return redirect(page.url + "#comments")
    if message:
        messages.error(request, message)
    return page.render(request, context_overrides={"comment_form": form})
