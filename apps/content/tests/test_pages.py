import json
import re

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from wagtail.models import Page

from apps.content.models import (
    AboutPage,
    ArticleKind,
    ArticlePage,
    ServicePage,
    SiteSettings,
)

pytestmark = pytest.mark.django_db

PAGES = [
    "/",
    "/about/",
    "/services/",
    "/services/service-1/",
    "/services/corporate/",
    "/blog/",
    "/blog/post-1/",
    "/blog/post-5/",
    "/blog/post-6/",
    "/portfolio/",
    "/contact/",
    "/terms/",
    "/privacy/",
]


@pytest.mark.parametrize("url", PAGES)
def test_every_page_renders(client, demo_site, url):
    response = client.get(url)
    assert response.status_code == 200
    html = response.content.decode()
    assert 'dir="rtl"' in html
    assert "Arezoo" in html  # brand from Site Settings in header/footer


def test_seed_is_idempotent_and_resettable(demo_site):
    pages = Page.objects.count()
    call_command("seed_demo", verbosity=0)
    assert Page.objects.count() == pages  # second run does nothing
    call_command("seed_demo", "--reset", verbosity=0)
    assert Page.objects.count() == pages  # recreated, not duplicated


def test_menu_and_whatsapp_come_from_settings(client, demo_site):
    html = client.get("/").content.decode()
    assert 'href="/blog/"' in html
    assert "https://wa.me/989120000000?text=" in html


def test_whatsapp_url_format(demo_site):
    settings = SiteSettings.objects.get()
    settings.whatsapp_message = ""
    assert settings.whatsapp_url == "https://wa.me/989120000000"
    settings.whatsapp_number = ""
    assert settings.whatsapp_url == ""


def test_service_shows_price_or_on_request(client, demo_site):
    assert "استعلام قیمت" in client.get("/services/service-1/").content.decode()
    assert "۲٬۵۰۰٬۰۰۰ تومان" in client.get("/services/service-4/").content.decode()


def test_team_section_hidden_by_default(client, demo_site):
    assert "عضو نمونه تیم" not in client.get("/about/").content.decode()
    about = AboutPage.objects.get()
    about.show_team = True
    about.save_revision().publish()
    assert "عضو نمونه تیم" in client.get("/about/").content.decode()


# --- validation --------------------------------------------------------------


def test_podcast_requires_audio(blog):
    page = ArticlePage(title="x", slug="x", intro="x", kind=ArticleKind.PODCAST)
    with pytest.raises(ValidationError) as exc:
        page.clean()
    assert "audio_url" in exc.value.message_dict


def test_video_requires_supported_url(blog):
    page = ArticlePage(
        title="x", slug="x", intro="x", kind=ArticleKind.VIDEO, video_url="https://vimeo.com/1"
    )
    with pytest.raises(ValidationError) as exc:
        page.clean()
    assert "video_url" in exc.value.message_dict


def test_service_price_cannot_be_negative(demo_site):
    page = ServicePage(title="x", slug="x", summary="x", price=-1)
    with pytest.raises(ValidationError):
        page.clean()


# --- magazine ------------------------------------------------------------------


def test_blog_filter_by_kind(client, blog):
    html = client.get("/blog/?kind=podcast").content.decode()
    assert "قسمت اول" in html
    assert "۵ اشتباه رایج" not in html


def test_blog_htmx_request_returns_only_the_list(client, blog):
    response = client.get("/blog/?kind=article", HTTP_HX_REQUEST="true")
    html = response.content.decode()
    assert response.status_code == 200
    assert "<html" not in html
    assert "card" in html


def test_reading_time_and_related(article):
    assert article.reading_minutes >= 1
    assert all(r.category_id == article.category_id for r in article.get_related())


def test_scheduled_article_goes_live_when_task_runs(blog):
    from datetime import timedelta

    from django.utils import timezone

    from apps.core.tasks import publish_scheduled

    page = ArticlePage(title="زمان‌بندی", slug="scheduled", intro="x", live=False)
    blog.add_child(instance=page)
    page.save_revision(approved_go_live_at=timezone.now() - timedelta(minutes=1))
    assert not ArticlePage.objects.get(pk=page.pk).live

    publish_scheduled()
    assert ArticlePage.objects.get(pk=page.pk).live


def test_publish_schedule_is_registered():
    from django_q.models import Schedule

    assert Schedule.objects.filter(func="apps.core.tasks.publish_scheduled", minutes=1).exists()


# --- search ------------------------------------------------------------------


def test_search_matches_arabic_yeh_variant(client, blog):
    # Title is written with Persian «ی»; the query uses Arabic «ي»
    html = client.get("/search/", {"q": "مدير"}).content.decode()
    assert "مدیر خوب، کارمند خوب را نگه می‌دارد" in html


def test_search_without_query(client, blog):
    assert client.get("/search/").status_code == 200


# --- SEO -------------------------------------------------------------------------


def test_meta_tags_and_structured_data(client, article):
    html = client.get(article.url).content.decode()
    assert '<meta property="og:type" content="article">' in html
    assert 'property="og:image"' in html
    assert (
        '<meta name="robots" content="noindex, nofollow">' in html
    )  # indexing off outside production
    blocks = [
        json.loads(b)
        for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html)
    ]
    types = {b["@type"] for b in blocks}
    assert {"Article", "BreadcrumbList"} <= types


def test_jsonld_cannot_break_out_of_script(client, article):
    article.title = "</script><script>alert(1)</script>"
    article.save_revision().publish()
    html = client.get(article.url).content.decode()
    assert "</script><script>alert(1)" not in html


def test_robots_blocks_everything_by_default(client):
    assert "Disallow: /\n" in client.get("/robots.txt").content.decode()


def test_robots_in_production_lists_sitemap(client, settings):
    settings.SEO_ALLOW_INDEXING = True
    body = client.get("/robots.txt").content.decode()
    assert "Disallow: /panel/" in body
    assert "Sitemap: http://testserver/sitemap.xml" in body


def test_sitemap_lists_pages(client, article):
    body = client.get("/sitemap.xml").content.decode()
    assert "/blog/post-1/" in body


def test_podcast_feed(client, blog):
    response = client.get("/blog/feed/podcast/")
    body = response.content.decode()
    assert response.status_code == 200
    assert 'xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"' in body
    assert (
        '<enclosure length="0" type="audio/mpeg" url="https://example.com/podcast/episode-1.mp3"'
        in body
    )
    assert "<itunes:episode>1</itunes:episode>" in body
    assert "۵ اشتباه رایج" not in body  # articles are not podcast episodes


def test_styleguide_only_in_debug(client, settings):
    settings.DEBUG = False
    assert client.get("/styleguide/").status_code == 404
