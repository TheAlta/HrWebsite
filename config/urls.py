from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.contrib.sitemaps.views import sitemap
from wagtail.documents import urls as wagtaildocs_urls

from apps.content import views as content_views
from apps.core.views import healthz

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path(settings.DJANGO_ADMIN_PATH, admin.site.urls),
    path(settings.WAGTAIL_ADMIN_PATH, include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    path("search/", content_views.search, name="search"),
    path("account/bookings/", include("apps.booking.urls")),
    path("account/registrations/", include("apps.events.urls")),
    path("account/", include("apps.accounts.urls")),
    path("orders/", include("apps.orders.urls")),
    path("payments/", include("apps.payments.urls")),
    path("leads/", include("apps.crm.urls")),
    path("", include("apps.shop.urls")),
    path("sitemap.xml", sitemap, name="sitemap"),
    path("robots.txt", content_views.robots_txt, name="robots_txt"),
    path("styleguide/", content_views.styleguide, name="styleguide"),
]

if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Wagtail's page serving must stay last: it catches every remaining URL
urlpatterns += [path("", include(wagtail_urls))]
