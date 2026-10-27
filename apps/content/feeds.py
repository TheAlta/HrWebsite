"""Podcast RSS feed with iTunes tags, so episodes can be listed in podcast apps (CMS-3)."""

from django.contrib.syndication.views import Feed
from django.utils.feedgenerator import Rss201rev2Feed

from .models import ArticleKind, ArticlePage
from .models.settings import SiteSettings

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"


class ITunesFeedGenerator(Rss201rev2Feed):
    def rss_attributes(self):
        return {**super().rss_attributes(), "xmlns:itunes": ITUNES_NS}

    def add_root_elements(self, handler):
        super().add_root_elements(handler)
        handler.addQuickElement("itunes:author", self.feed["author_name"] or "")
        handler.addQuickElement("itunes:explicit", "false")
        if self.feed.get("itunes_image"):
            handler.addQuickElement("itunes:image", "", {"href": self.feed["itunes_image"]})
        handler.addQuickElement("itunes:category", "", {"text": "Business"})

    def add_item_elements(self, handler, item):
        super().add_item_elements(handler, item)
        if item.get("itunes_duration"):
            handler.addQuickElement("itunes:duration", item["itunes_duration"])
        if item.get("itunes_episode"):
            handler.addQuickElement("itunes:episode", str(item["itunes_episode"]))


class PodcastFeed(Feed):
    feed_type = ITunesFeedGenerator

    def __init__(self, blog_page):
        super().__init__()
        self.blog_page = blog_page
        self.request = None

    def __call__(self, request, *args, **kwargs):
        self.request = request
        return super().__call__(request, *args, **kwargs)

    def _settings(self):
        return SiteSettings.for_request(self.request)

    def title(self):
        return self.blog_page.podcast_title or f"پادکست {self._settings().brand_name}"

    def link(self):
        return self.blog_page.url

    def description(self):
        return self.blog_page.podcast_description or self.blog_page.intro or self.title()

    def author_name(self):
        return self._settings().brand_name

    def feed_extra_kwargs(self, obj):
        cover = self.blog_page.podcast_cover
        image = (
            self.request.build_absolute_uri(cover.get_rendition("fill-1400x1400").url)
            if cover
            else ""
        )
        return {"itunes_image": image}

    def items(self):
        return (
            ArticlePage.objects.child_of(self.blog_page)
            .live()
            .filter(kind=ArticleKind.PODCAST)
            .order_by("-first_published_at")[:100]
        )

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.intro

    def item_link(self, item):
        return item.url

    def item_pubdate(self, item):
        return item.first_published_at

    def item_enclosure_url(self, item):
        src = item.audio_src
        return self.request.build_absolute_uri(src) if src else None

    def item_enclosure_length(self, item):
        if item.audio_file:
            try:
                return item.audio_file.file.size
            except (OSError, ValueError):
                return 0
        return 0

    def item_enclosure_mime_type(self, item):
        return "audio/mpeg"

    def item_extra_kwargs(self, item):
        return {"itunes_duration": item.duration, "itunes_episode": item.episode_number}
