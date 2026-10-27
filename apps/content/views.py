from django.conf import settings
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_GET

from apps.core.text import normalize_for_search

from .models import ArticlePage

SEARCH_RESULTS_PER_PAGE = 10


@require_GET
def search(request):
    """Magazine search (CMS-4). Query and index are both normalised, so «علي» finds «علی»."""
    query = request.GET.get("q", "").strip()[:100]
    page_obj = None
    if query:
        results = ArticlePage.objects.live().search(normalize_for_search(query))
        paginator = Paginator(results, SEARCH_RESULTS_PER_PAGE)
        try:
            page_obj = paginator.page(request.GET.get("page", 1))
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)
    return render(request, "content/search.html", {"query": query, "page_obj": page_obj})


@require_GET
@cache_page(60 * 60)
def robots_txt(request):
    sitemap = request.build_absolute_uri("/sitemap.xml")
    if settings.SEO_ALLOW_INDEXING:
        lines = [
            "User-agent: *",
            f"Disallow: /{settings.WAGTAIL_ADMIN_PATH}",
            f"Disallow: /{settings.DJANGO_ADMIN_PATH}",
            "Disallow: /search/",
            "",
            f"Sitemap: {sitemap}",
        ]
    else:
        # Development and staging must never be indexed
        lines = ["User-agent: *", "Disallow: /"]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


@require_GET
def styleguide(request):
    """Every shared UI component on one page — for review during development only."""
    if not settings.DEBUG:
        raise Http404
    return render(request, "styleguide.html")
