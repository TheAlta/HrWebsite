"""Tags for layout and SEO: share image, structured data (JSON-LD), menu state."""

import json

from django import template
from django.utils.html import format_html, strip_tags
from django.utils.safestring import mark_safe
from django.utils.text import Truncator

register = template.Library()


@register.simple_tag(takes_context=True)
def meta_description(context, page):
    """The page's own description, else its intro or summary, else the site's own words.

    Search engines show this under the title; a page without one gets a guess.
    """
    for value in (
        page.search_description,
        getattr(page, "intro", ""),
        getattr(page, "summary", ""),
    ):
        text = " ".join(strip_tags(str(value or "")).split())
        if text:
            return Truncator(text).chars(160)
    site_settings = context.get("settings")
    if not site_settings:
        return ""
    site = site_settings["content"]["SiteSettings"]
    return " ".join(f"{site.tagline}. {site.footer_text}".strip(". ").split())[:160]


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


@register.simple_tag(takes_context=True)
def group_active(context, group):
    """'true' when the current URL is inside any link of a menu group."""
    return "true" if any(is_active(context, link.href) for link in group["links"]) else ""


@register.filter
def menu_links(menu):
    """The plain links of the main menu, without its dropdown groups."""
    return [item.value for item in menu if item.block_type == "link"]


SCENES = ("scene-window", "scene-window-1", "scene-window-2")


@register.filter
def scene_class(obj):
    """A drawn picture for a card without a photo; the same one for an object every time."""
    return SCENES[(obj.pk or 0) % len(SCENES)]


@register.simple_tag
def split_highlight(text, word):
    """(before, word, after) around the first place `word` appears in `text`, or None.

    For a title with one marked word; the template escapes each part.
    """
    if not word or word not in (text or ""):
        return None
    before, _, after = text.partition(word)
    return (before, word, after)


BOOK_COVERS = 5


@register.filter
def cover_class(obj):
    """A drawn cover colour for a product without a cover image; the same one every time."""
    return f"book-cover-{(obj.pk or 0) % BOOK_COVERS + 1}"


@register.simple_tag(takes_context=True)
def legal_pages(context):
    """Live legal pages of this site, linked from the footer."""
    from wagtail.models import Site

    from ..models import LegalPage

    request = context.get("request")
    site = Site.find_for_request(request) if request else None
    pages = LegalPage.objects.live().public()
    if site:
        pages = pages.descendant_of(site.root_page)
    return pages.order_by("path")


@register.simple_tag(name="jsonld")
def _jsonld(data):
    # Escape "<" so content can never close the <script> element
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    return format_html(
        '<script type="application/ld+json">{}</script>',
        mark_safe(payload),  # noqa: S308 — JSON with "<" escaped above
    )


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

    return mark_safe("".join(_jsonld(b) for b in blocks))  # noqa: S308 — each is built safe above
