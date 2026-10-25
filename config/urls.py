from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

from apps.core.views import healthz

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path(settings.DJANGO_ADMIN_PATH, admin.site.urls),
    path(settings.WAGTAIL_ADMIN_PATH, include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
]

if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Wagtail's page serving must stay last: it catches every remaining URL
urlpatterns += [path("", include(wagtail_urls))]
