"""Template filters available in every template (registered as a builtin in settings).

{{ article.published_at|jdate }}       -> ۳ آبان ۱۴۰۵
{{ booking.start_at|jdatetime }}       -> ۳ آبان ۱۴۰۵، ساعت ۱۴:۳۰
{{ order.total|toman }}                -> ۱٬۲۰۰٬۰۰۰ تومان
{{ count|fa_digits }}                  -> ۱۲
"""

from django import template
from django.conf import settings
from django.utils import timezone

from apps.core import jalali, money, text

register = template.Library()


@register.filter
def jdate(value, arg=""):
    if value in (None, ""):
        return ""
    return jalali.format_date(value, weekday=arg == "weekday")


@register.filter
def jdatetime(value):
    if value in (None, ""):
        return ""
    return jalali.format_datetime(value)


@register.filter
def jtime(value):
    if value in (None, ""):
        return ""
    return jalali.format_time(value)


@register.filter
def unix(value):
    """Whole-second Unix timestamp, for passing a moment through a URL or form."""
    return int(value.timestamp())


@register.filter
def toman(value):
    if value in (None, ""):
        return ""
    return money.format_toman(value)


@register.filter
def fa_digits(value):
    if value is None:
        return ""
    return text.to_fa_digits(value)


@register.simple_tag
def now_jalali():
    return jalali.format_date(timezone.now(), weekday=True)


@register.simple_tag
def now_jalali_year():
    return text.to_fa_digits(jalali.to_jalali(timezone.localdate()).year)


@register.simple_tag
def site_name():
    return settings.WAGTAIL_SITE_NAME
