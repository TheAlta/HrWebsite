"""Tags for layout and SEO: share image, structured data (JSON-LD), menu state."""

import json

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag(takes_context=True)
def share_image_url(context, page=None):
    """Absolute URL of the 1200×630 share image: page image, else the site default."""
    request = context["request"]
    image = (
        page.get_share_image() if page is not None and hasattr(page, "get_share_image") else None
    )
    if image is None:
        site_settings = context.get("settings")
        image = site_settings["content"]["SiteSettings"].default_og_image if site_settings else None
    if image is None:
        return ""
    return request.build_absolute_uri(image.get_rendition("fill-1200x630|format-jpeg").url)


@register.simple_tag(takes_context=True)
def is_active(context, href):
    """'true' when the current URL is inside href — used for aria-current in the menu."""
    path = context["request"].path
    if not href:
        return ""
    if href == "/":
        return "true" if path == "/" else ""
    return "true" if path.startswith(href) else ""


@register.simple_tag(name="jsonld")
def _jsonld(data):
    # Escape "<" so content can never close the <script> element
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    return format_html('<script type="application/ld+json">{}</script>', mark_safe(payload))


@register.simple_tag(takes_context=True)
def page_jsonld(context, page):
    """schema.org data for the page (spec section 4, SEO): Person on the home page,
    Article for magazine posts, BreadcrumbList everywhere else."""
    from apps.content.models import ArticlePage, HomePage

    request = context["request"]
    site_settings = context["settings"]["content"]["SiteSettings"]
    url = request.build_absolute_uri(page.url)
    blocks = []

    if isinstance(page, HomePage):
        same_as = [link["url"] for link in site_settings.social_links]
        blocks.append(
            {
                "@context": "https://schema.org",
                "@type": "Person",
                "name": site_settings.brand_name,
                "url": url,
                "jobTitle": "مشاور منابع انسانی",
                **({"sameAs": same_as} if same_as else {}),
            }
        )
    else:
        crumbs = [*page.get_breadcrumbs(), page]
        blocks.append(
            {
                "@context": "https://schema.org",
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i,
                        "name": crumb.title,
                        "item": request.build_absolute_uri(crumb.url),
                    }
                    for i, crumb in enumerate(crumbs, start=1)
                ],
            }
        )

    if isinstance(page, ArticlePage):
        article = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": page.title,
            "description": page.search_description or page.intro,
            "url": url,
            "author": {"@type": "Person", "name": site_settings.brand_name},
        }
        if page.first_published_at:
            article["datePublished"] = page.first_published_at.isoformat()
        if page.last_published_at:
            article["dateModified"] = page.last_published_at.isoformat()
        image = share_image_url(context, page)
        if image:
            article["image"] = image
        blocks.append(article)

    if hasattr(page, "extra_jsonld"):
        blocks.append(page.extra_jsonld(url))

    return mark_safe("".join(_jsonld(b) for b in blocks))
