from django.db import connection
from django.http import HttpResponsePermanentRedirect, JsonResponse
from django.templatetags.static import static
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@never_cache
@require_GET
def healthz(request):
    """Liveness/readiness probe for uptime monitoring: 200 when the database answers."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "error", "database": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


@require_GET
def favicon(request):
    """Some clients ask for /favicon.ico without reading the page's <link rel="icon">."""
    return HttpResponsePermanentRedirect(static("favicon.svg"))
