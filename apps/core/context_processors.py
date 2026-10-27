from django.conf import settings


def site(request):
    """Values every template needs that are not editable in the panel."""
    return {
        "SEO_ALLOW_INDEXING": settings.SEO_ALLOW_INDEXING,
        "WAGTAIL_ADMIN_PATH": settings.WAGTAIL_ADMIN_PATH,
    }
