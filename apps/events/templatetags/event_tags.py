"""Event pieces every page can show."""

from django import template
from django.utils import timezone

register = template.Library()

# Set by the bar's close button (static/js/site.js) for the rest of the visit
BAR_CLOSED_COOKIE = "event_bar_closed"


@register.simple_tag(takes_context=True)
def event_bar(context):
    """The next free public course or webinar for the bar above the header (REPORT #058).

    None when there is none, or when the visitor closed the bar for this event:
    the server leaves it out, so the page does not jump after it loads.
    """
    from apps.events.models import EventPage

    event = (
        EventPage.objects.live()
        .public()
        .exclude(kind=EventPage.Kind.TALK)
        .filter(price=0, start_at__gt=timezone.now())
        .order_by("start_at")
        .first()
    )
    request = context.get("request")
    if event and request and request.COOKIES.get(BAR_CLOSED_COOKIE) == str(event.pk):
        return None
    return event
