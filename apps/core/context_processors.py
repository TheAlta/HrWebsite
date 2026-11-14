from django.conf import settings

THEMES = ("light", "dark")


def site(request):
    """Values every template needs that are not editable in the panel."""
    theme = request.COOKIES.get("theme")
    return {
        "SEO_ALLOW_INDEXING": settings.SEO_ALLOW_INDEXING,
        "WAGTAIL_ADMIN_PATH": settings.WAGTAIL_ADMIN_PATH,
        # Set by the theme switch (static/js/site.js); unset follows the device
        "theme": theme if theme in THEMES else "",
    }
