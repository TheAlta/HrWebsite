from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.http import hashed_ip

from . import services
from .forms import SubscribeForm
from .models import Subscriber

# Where a form can sit: its own markup comes back, and the subscriber's source says where
PLACES = {
    "footer": "newsletter/includes/subscribe_form.html",
    "home": "newsletter/includes/subscribe_band.html",
}


@require_POST
def subscribe(request):
    """The footer form, or the home page's band (REPORT #058).

    HTMX swaps the form for the result; without JavaScript a page shows it.
    """
    form = SubscribeForm(request.POST)
    place = request.POST.get("place")
    if place not in PLACES:
        place = "footer"
    template = PLACES[place]
    context = {"newsletter_form": form}
    if form.is_bot:
        context["done"] = True  # pretend success, save nothing
    elif form.is_valid():
        try:
            services.subscribe(
                email=form.cleaned_data["email"],
                mobile=form.cleaned_data["mobile"],
                source=place,
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
