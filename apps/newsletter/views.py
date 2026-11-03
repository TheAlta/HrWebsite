from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.http import hashed_ip

from . import services
from .forms import SubscribeForm
from .models import Subscriber


@require_POST
def subscribe(request):
    """The footer form. HTMX swaps the form for the result; without JavaScript a page shows it."""
    form = SubscribeForm(request.POST)
    template = "newsletter/includes/subscribe_form.html"
    context = {"newsletter_form": form}
    if form.is_bot:
        context["done"] = True  # pretend success, save nothing
    elif form.is_valid():
        try:
            services.subscribe(
                email=form.cleaned_data["email"],
                mobile=form.cleaned_data["mobile"],
                source="footer",
                ip_hash=hashed_ip(request),
            )
            context["done"] = True
        except services.RateLimited:
            context["error"] = "تعداد درخواست‌ها زیاد است. چند دقیقه دیگر تلاش کنید."
    if request.htmx:
        return render(request, template, context)
    return render(request, "newsletter/result.html", context)


@require_http_methods(["GET", "POST"])
def unsubscribe(request, token):
    """GET only asks: mail scanners open links, and must not unsubscribe anyone."""
    subscriber = get_object_or_404(Subscriber, token=token)
    if request.method == "POST":
        services.unsubscribe(subscriber)
        return render(request, "newsletter/unsubscribe.html", {"done": True})
    return render(request, "newsletter/unsubscribe.html", {"subscriber": subscriber})
