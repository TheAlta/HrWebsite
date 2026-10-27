import math

from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import models
from django.http import Http404
from django.utils.html import strip_tags
from modelcluster.contrib.taggit import ClusterTaggableManager
from modelcluster.fields import ParentalKey
from taggit.models import TaggedItemBase
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.contrib.routable_page.models import RoutablePageMixin, path, re_path
from wagtail.fields import StreamField
from wagtail.search import index
from wagtail.snippets.models import register_snippet

from apps.core.embeds import parse_video_url
from apps.core.text import normalize_for_search

from ..blocks import BodyBlock, DocumentBlock
from .base import BasePage

ARTICLES_PER_PAGE = 9
WORDS_PER_MINUTE = 200


@register_snippet
class Category(models.Model):
    name = models.CharField("نام", max_length=100)
    slug = models.SlugField("نامک", max_length=100, unique=True, allow_unicode=True)
    description = models.TextField("توضیح", blank=True)

    panels = [FieldPanel("name"), FieldPanel("slug"), FieldPanel("description")]

    class Meta:
        verbose_name = "دسته‌بندی"
        verbose_name_plural = "دسته‌بندی‌ها"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ArticleTag(TaggedItemBase):
    content_object = ParentalKey(
        "content.ArticlePage", on_delete=models.CASCADE, related_name="tagged_items"
    )


class ArticleKind(models.TextChoices):
    ARTICLE = "article", "مقاله"
    PODCAST = "podcast", "پادکست"
    VIDEO = "video", "ویدئو"


class BlogIndexPage(RoutablePageMixin, BasePage):
    """/blog — the magazine: articles, podcast and video with filters (spec section 2)."""

    intro = models.TextField("مقدمه", blank=True)
    podcast_title = models.CharField("نام پادکست", max_length=200, blank=True)
    podcast_description = models.TextField("توضیح پادکست", blank=True)
    podcast_cover = models.ForeignKey(
        "wagtailimages.Image",
        verbose_name="کاور پادکست",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="مربع، حداقل ۱۴۰۰×۱۴۰۰ (الزام اپ‌های پادکست)",
    )

    content_panels = [
        *BasePage.content_panels,
        FieldPanel("intro"),
        MultiFieldPanel(
            [
                FieldPanel("podcast_title"),
                FieldPanel("podcast_description"),
                FieldPanel("podcast_cover"),
            ],
            heading="فید پادکست",
        ),
    ]

    max_count = 1
    parent_page_types = ["content.HomePage"]
    subpage_types = ["content.ArticlePage"]

    class Meta:
        verbose_name = "مجله"

    def get_articles(self):
        return (
            ArticlePage.objects.child_of(self)
            .live()
            .select_related("cover_image", "category")
            .order_by("-first_published_at")
        )

    def filter_articles(self, request):
        """Apply ?kind=, ?category= and ?tag= filters. Returns (queryset, active filters)."""
        articles = self.get_articles()
        active = {}
        kind = request.GET.get("kind")
        if kind in ArticleKind.values:
            articles = articles.filter(kind=kind)
            active["kind"] = kind
        category_slug = request.GET.get("category")
        if category_slug:
            category = Category.objects.filter(slug=category_slug).first()
            if category:
                articles = articles.filter(category=category)
                active["category"] = category
        tag = request.GET.get("tag")
        if tag:
            articles = articles.filter(tags__name=tag)
            active["tag"] = tag
        return articles, active

    @path("")
    def index_route(self, request):  # overrides RoutablePageMixin's default "" route
        articles, active = self.filter_articles(request)
        paginator = Paginator(articles, ARTICLES_PER_PAGE)
        try:
            page_obj = paginator.page(request.GET.get("page", 1))
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)
        context = {
            "page_obj": page_obj,
            "articles": page_obj.object_list,
            "active": active,
            "kinds": ArticleKind.choices,
            "categories": Category.objects.all(),
        }
        # HTMX filter/pagination requests only need the list fragment
        if getattr(request, "htmx", False) and not request.htmx.boosted:
            template = "content/includes/article_list.html"
            return self.render(request, context_overrides=context, template=template)
        return self.render(request, context_overrides=context)

    @path("feed/podcast/", name="podcast_feed")
    def podcast_feed(self, request):
        from ..feeds import PodcastFeed

        return PodcastFeed(self)(request)


class ArticlePage(RoutablePageMixin, BasePage):
    kind = models.CharField(
        "نوع", max_length=20, choices=ArticleKind.choices, default=ArticleKind.ARTICLE
    )
    category = models.ForeignKey(
        Category,
        verbose_name="دسته",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="articles",
    )
    tags = ClusterTaggableManager("برچسب‌ها", through=ArticleTag, blank=True)
    cover_image = models.ForeignKey(
        "wagtailimages.Image",
        verbose_name="تصویر شاخص",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    intro = models.TextField("خلاصه", max_length=400)
    body = StreamField(BodyBlock(), blank=True, verbose_name="متن")

    # Podcast
    audio_file = models.ForeignKey(
        "wagtaildocs.Document",
        verbose_name="فایل صوتی",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="MP3 آپلودی. یا به‌جای آن «آدرس فایل صوتی» را پر کنید.",
    )
    audio_url = models.URLField("آدرس فایل صوتی", blank=True)
    duration = models.CharField("مدت", max_length=8, blank=True, help_text="مثل 45:12 یا 1:05:00")
    episode_number = models.PositiveIntegerField("شماره قسمت", null=True, blank=True)

    # Video
    video_url = models.URLField("آدرس ویدئو", blank=True, help_text="لینک آپارات یا یوتیوب")

    attachments = StreamField(
        [("document", DocumentBlock())], blank=True, verbose_name="فایل‌های پیوست"
    )
    allow_comments = models.BooleanField("امکان ثبت نظر", default=True)

    content_panels = [
        *BasePage.content_panels,
        MultiFieldPanel(
            [FieldPanel("kind"), FieldPanel("category"), FieldPanel("tags")], heading="دسته‌بندی"
        ),
        FieldPanel("cover_image"),
        FieldPanel("intro"),
        FieldPanel("body"),
        MultiFieldPanel(
            [
                FieldPanel("audio_file"),
                FieldPanel("audio_url"),
                FieldPanel("duration"),
                FieldPanel("episode_number"),
            ],
            heading="پادکست",
            classname="collapsed",
        ),
        MultiFieldPanel([FieldPanel("video_url")], heading="ویدئو", classname="collapsed"),
        FieldPanel("attachments"),
        FieldPanel("allow_comments"),
    ]
    search_fields = [
        *BasePage.search_fields,
        index.SearchField("search_text"),
        index.FilterField("kind"),
    ]

    parent_page_types = ["content.BlogIndexPage"]
    subpage_types = []
    og_type = "article"

    class Meta:
        verbose_name = "مطلب مجله"
        verbose_name_plural = "مطالب مجله"

    def clean(self):
        super().clean()
        errors = {}
        if self.kind == ArticleKind.PODCAST and not (self.audio_file or self.audio_url):
            errors["audio_url"] = "پادکست باید فایل صوتی یا آدرس فایل صوتی داشته باشد."
        if self.video_url and not parse_video_url(self.video_url):
            errors["video_url"] = "فقط لینک آپارات یا یوتیوب پشتیبانی می‌شود."
        if self.kind == ArticleKind.VIDEO and not self.video_url:
            errors["video_url"] = "ویدئو باید آدرس ویدئو داشته باشد."
        if errors:
            raise ValidationError(errors)

    def get_share_image(self):
        return self.og_image or self.cover_image

    # --- derived values -------------------------------------------------

    def body_text(self):
        parts = []
        for block in self.body:
            if block.block_type == "paragraph":
                parts.append(strip_tags(block.value.source))
            elif block.block_type == "heading":
                parts.append(block.value)
            elif block.block_type == "quote":
                parts.append(block.value["text"])
        return " ".join(parts)

    def search_text(self):
        """Normalised text so «علي» finds «علی» (spec CMS-4)."""
        return normalize_for_search(f"{self.title} {self.intro} {self.body_text()}")

    @property
    def reading_minutes(self):
        words = len(f"{self.intro} {self.body_text()}".split())
        return max(1, math.ceil(words / WORDS_PER_MINUTE))

    @property
    def video(self):
        return parse_video_url(self.video_url) if self.video_url else None

    @property
    def audio_src(self):
        return self.audio_file.url if self.audio_file else self.audio_url

    def get_related(self, limit=3):
        related = ArticlePage.objects.live().exclude(pk=self.pk).order_by("-first_published_at")
        if self.category_id:
            related = related.filter(category_id=self.category_id)
        return related.select_related("cover_image")[:limit]

    # --- views ----------------------------------------------------------

    def get_context(self, request, *args, **kwargs):
        from ..forms import CommentForm

        context = super().get_context(request, *args, **kwargs)
        context["comments"] = self.comments.filter(status=Comment.Status.APPROVED)
        context["comment_form"] = kwargs.get("comment_form") or CommentForm()
        context["related"] = self.get_related()
        return context

    @re_path(r"^comment/$", name="comment")
    def submit_comment(self, request):
        from .. import comments

        if request.method != "POST" or not self.allow_comments:
            raise Http404
        return comments.handle_submission(self, request)


class Comment(models.Model):
    """Reader comment, shown only after an admin approves it (CMS-5)."""

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار تأیید"
        APPROVED = "approved", "تأییدشده"
        SPAM = "spam", "اسپم"

    page = models.ForeignKey(
        ArticlePage, verbose_name="مطلب", on_delete=models.CASCADE, related_name="comments"
    )
    name = models.CharField("نام", max_length=80)
    email = models.EmailField("ایمیل", blank=True, help_text="نمایش داده نمی‌شود.")
    text = models.TextField("متن", max_length=2000)
    status = models.CharField(
        "وضعیت", max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    # Salted hash, not the raw IP: enough for rate limiting, nothing personal stored
    ip_hash = models.CharField(max_length=64, db_index=True, editable=False)
    created_at = models.DateTimeField("زمان ثبت", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "نظر"
        verbose_name_plural = "نظرها"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.name}: {self.text[:40]}"
