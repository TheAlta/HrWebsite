import datetime as dt

from django.template import Context, Template


def render(source, **context):
    return Template(source).render(Context(context))


def test_filters_render_persian():
    assert render("{{ d|jdate }}", d=dt.date(2026, 10, 25)) == "۳ آبان ۱۴۰۵"
    assert render("{{ d|jdate:'weekday' }}", d=dt.date(2026, 10, 25)) == "یکشنبه ۳ آبان ۱۴۰۵"
    value = dt.datetime(2026, 10, 25, 10, 0, tzinfo=dt.UTC)
    assert render("{{ v|jdatetime }}", v=value) == "۳ آبان ۱۴۰۵، ساعت ۱۳:۳۰"
    assert render("{{ a|toman }}", a=12_000_000) == "۱٬۲۰۰٬۰۰۰ تومان"
    assert render("{{ n|fa_digits }}", n=42) == "۴۲"


def test_filters_are_empty_for_missing_values():
    for name in ("jdate", "jdatetime", "toman", "fa_digits"):
        assert render(f"{{{{ v|{name} }}}}", v=None) == ""


def test_site_name_tag(settings):
    settings.WAGTAIL_SITE_NAME = "سایت تست"
    assert render("{% site_name %}") == "سایت تست"
