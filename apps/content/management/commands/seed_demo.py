"""Fill the site with sample content so every page can be reviewed and tested.

    docker compose exec web python manage.py seed_demo           # only if the site is empty
    docker compose exec web python manage.py seed_demo --reset   # delete sample content first

All text is placeholder; the owner replaces it from the panel.
"""

import datetime as dt
import io
import random

from django.conf import settings as django_settings
from django.core.files.images import ImageFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from PIL import Image as PILImage
from PIL import ImageDraw
from wagtail.documents import get_document_model
from wagtail.images import get_image_model
from wagtail.models import Page, Site
from wagtail.rich_text import RichText

from apps.booking.models import Availability, Booking, BookingPage, SessionType
from apps.content.models import (
    AboutPage,
    ArticleKind,
    ArticlePage,
    Audience,
    BlogIndexPage,
    Category,
    Comment,
    ContactPage,
    CorporateServicesPage,
    HomePage,
    LegalPage,
    ServiceIndexPage,
    ServicePage,
    SiteSettings,
    TeamMember,
)
from apps.crm.models import ConsultationPage
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.portfolio.models import Client, PortfolioPage, Project, Testimonial

DEMO_TAG = "[demo]"  # marks sample images/documents so --reset can remove them

PALETTE = [
    ("#1c3970", "#2f5aa8"),
    ("#172e59", "#839fd9"),
    ("#a5650b", "#e59a1a"),
    ("#22468a", "#b3c6ea"),
]


def make_image(title, size=(1200, 800), seed=0):
    """A simple generated picture (gradient + circles) — no network or stock photos needed."""
    rnd = random.Random(seed)
    start, end = PALETTE[seed % len(PALETTE)]
    img = PILImage.new("RGB", size, start)
    draw = ImageDraw.Draw(img)
    s, e = (
        PILImage.new("RGB", (1, 1), start).getpixel((0, 0)),
        PILImage.new("RGB", (1, 1), end).getpixel((0, 0)),
    )
    for y in range(size[1]):
        t = y / size[1]
        draw.line(
            [(0, y), (size[0], y)], fill=tuple(int(s[i] + (e[i] - s[i]) * t) for i in range(3))
        )
    for _ in range(6):
        r = rnd.randint(40, 220)
        x, y = rnd.randint(0, size[0]), rnd.randint(0, size[1])
        draw.ellipse([x - r, y - r, x + r, y + r], outline=(255, 255, 255), width=3)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    return get_image_model().objects.create(
        title=f"{title} {DEMO_TAG}", file=ImageFile(buffer, name=f"demo-{seed}.jpg")
    )


def make_logo(name, seed):
    img = PILImage.new("RGB", (320, 120), "white")
    draw = ImageDraw.Draw(img)
    color = PALETTE[seed % len(PALETTE)][0]
    draw.rounded_rectangle([10, 20, 100, 100], radius=18, fill=color)
    draw.rectangle([120, 45, 300, 60], fill=color)
    draw.rectangle([120, 72, 240, 82], fill="#94a3b8")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return get_image_model().objects.create(
        title=f"لوگو {name} {DEMO_TAG}", file=ImageFile(buffer, name=f"logo-{seed}.png")
    )


def make_pdf(title):
    img = PILImage.new("RGB", (595, 842), "white")
    ImageDraw.Draw(img).rectangle([40, 40, 555, 120], fill="#1c3970")
    buffer = io.BytesIO()
    img.save(buffer, format="PDF")
    return get_document_model().objects.create(
        title=f"{title} {DEMO_TAG}",
        file=SimpleUploadedFile(
            "resume-demo.pdf", buffer.getvalue(), content_type="application/pdf"
        ),
    )


def p(text):
    return RichText(f"<p>{text}</p>")


def publish(parent, page):
    parent.add_child(instance=page)
    page.save_revision().publish()
    return page


LOREM = (
    "این متن نمونه است و از پنل مدیریت قابل تغییر است. منابع انسانی قلب هر سازمان است و "
    "تصمیم‌های درست در جذب، نگهداشت و توسعه افراد، مستقیم روی نتیجه کسب‌وکار اثر می‌گذارد."
)


class Command(BaseCommand):
    help = "Create sample pages, settings and snippets for development and review."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true", help="Delete existing sample content first."
        )

    @transaction.atomic
    def handle(self, *args, reset=False, **options):
        if not django_settings.ALLOW_SEED_DEMO:
            raise CommandError("seed_demo is disabled here (ALLOW_SEED_DEMO=false).")
        home = HomePage.objects.first()
        if home is None:
            self.stderr.write("HomePage not found. Run migrations first.")
            return
        if reset:
            home = self._reset(home)
        elif home.get_children().exists():
            self.stdout.write(
                "Site already has pages; nothing done. Use --reset to recreate sample content."
            )
            return

        images = [make_image(f"تصویر نمونه {i}", seed=i) for i in range(8)]
        portrait = make_image("پرتره", size=(800, 960), seed=11)

        clients = [
            Client.objects.create(name=name, logo=make_logo(name, i), show_logo=True, sort_order=i)
            for i, name in enumerate(
                ["شرکت آلفا", "گروه صنعتی بتا", "هلدینگ گاما", "بانک دلتا", "استارتاپ اپسیلون"]
            )
        ]
        testimonials = [
            Testimonial.objects.create(
                author_name=name,
                author_title=title,
                client=client,
                quote=quote,
                is_featured=True,
                consent_received=True,
            )
            for name, title, client, quote in [
                (
                    "مریم احمدی",
                    "مدیر منابع انسانی",
                    clients[0],
                    "طراحی نظام ارزیابی عملکرد، گفت‌وگوی مدیران و کارکنان را واقعاً تغییر داد.",
                ),
                (
                    "رضا کریمی",
                    "مدیرعامل",
                    clients[1],
                    "ساختار سازمانی جدید، تصمیم‌گیری را سریع‌تر و مسئولیت‌ها را روشن کرد.",
                ),
                (
                    "سارا محمدی",
                    "کارشناس ارشد آموزش",
                    clients[2],
                    "دوره آموزشی کاملاً کاربردی بود و همان هفته در تیم اجرایش کردیم.",
                ),
            ]
        ]
        projects = [
            Project.objects.create(
                title=title,
                client=client,
                image=images[i],
                summary=summary,
                year=year,
                results=p("کاهش ۳۰ درصدی خروج کارکنان در سال اول"),
                is_featured=True,
                sort_order=i,
            )
            for i, (title, client, summary, year) in enumerate(
                [
                    (
                        "بازطراحی نظام ارزیابی عملکرد",
                        clients[0],
                        "طراحی و استقرار ارزیابی ۳۶۰ درجه برای ۴۰۰ نفر.",
                        "۱۴۰۳",
                    ),
                    (
                        "طراحی ساختار سازمانی",
                        clients[1],
                        "بازطراحی چارت و شرح شغل‌ها پس از ادغام دو واحد.",
                        "۱۴۰۲",
                    ),
                    (
                        "برنامه توسعه مدیران میانی",
                        clients[2],
                        "دوره شش‌ماهه کوچینگ و آموزش برای ۲۵ مدیر.",
                        "۱۴۰۳",
                    ),
                ]
            )
        ]

        # --- pages ---------------------------------------------------------
        resume = make_pdf("رزومه")
        about = publish(
            home,
            AboutPage(
                title="درباره من",
                slug="about",
                headline="سلام، من آرزو هستم",
                intro=p(
                    "مشاور منابع انسانی با بیش از ۱۵ سال تجربه در سازمان‌های تولیدی، خدماتی و فناوری."
                ),
                photo=portrait,
                body=[
                    ("heading", "داستان من"),
                    ("paragraph", p(LOREM)),
                    ("paragraph", p(LOREM)),
                    (
                        "lead_magnet",
                        {
                            "title": "دریافت رزومه کامل",
                            "text": "رزومه و فهرست پروژه‌ها را دریافت کنید.",
                            "document": resume,
                            "button_label": "دریافت رزومه",
                        },
                    ),
                ],
                expertise=[
                    ("item", t)
                    for t in [
                        "ارزیابی عملکرد",
                        "طراحی ساختار سازمانی",
                        "جذب و استخدام",
                        "آموزش و توسعه مدیران",
                    ]
                ],
                credentials=[
                    (
                        "credential",
                        {
                            "title": "کارشناسی ارشد مدیریت منابع انسانی",
                            "issuer": "دانشگاه تهران",
                            "year": "۱۳۹۰",
                        },
                    )
                ],
                resume=resume,
            ),
        )
        services_index = publish(
            home, ServiceIndexPage(title="خدمات", slug="services", intro=p("خدمات فردی و سازمانی."))
        )
        services = []
        for i, (title, audience, summary, price) in enumerate(
            [
                (
                    "ارزیابی عملکرد",
                    Audience.CORPORATE,
                    "طراحی و استقرار نظام ارزیابی عملکرد منصفانه و قابل اجرا.",
                    None,
                ),
                (
                    "طراحی ساختار سازمانی",
                    Audience.CORPORATE,
                    "چارت، شرح شغل و جریان تصمیم‌گیری متناسب با استراتژی.",
                    None,
                ),
                (
                    "جذب و استخدام",
                    Audience.CORPORATE,
                    "فرایند جذب از شرح شغل تا مصاحبه ساختاریافته.",
                    None,
                ),
                (
                    "مشاوره مسیر شغلی",
                    Audience.INDIVIDUAL,
                    "جلسه فردی برای انتخاب مسیر، رزومه و آمادگی مصاحبه.",
                    25_000_000,
                ),
            ]
        ):
            services.append(
                publish(
                    services_index,
                    ServicePage(
                        title=title,
                        slug=f"service-{i + 1}",
                        audience=audience,
                        summary=summary,
                        cover_image=images[i],
                        price=price,
                        duration="۴ جلسه ۹۰ دقیقه‌ای",
                        is_featured=True,
                        problem=p(LOREM),
                        approach=p(LOREM),
                        deliverables=[
                            ("item", t)
                            for t in ["گزارش وضعیت موجود", "طرح اجرایی", "همراهی در استقرار"]
                        ],
                        testimonial=testimonials[i % 3],
                        case_study=projects[i % 3],
                    ),
                )
            )
        publish(
            services_index,
            CorporateServicesPage(
                title="خدمات سازمانی",
                slug="corporate",
                intro=p("برای سازمان‌هایی که می‌خواهند منابع انسانی را به مزیت رقابتی تبدیل کنند."),
            ),
        )

        blog = publish(
            home,
            BlogIndexPage(
                title="مجله",
                slug="blog",
                intro="مقاله، پادکست و ویدئو درباره منابع انسانی.",
                podcast_title="پادکست منابع انسانی",
            ),
        )
        categories = [
            Category.objects.create(name=name, slug=slug)
            for name, slug in [
                ("ارزیابی عملکرد", "performance"),
                ("رهبری", "leadership"),
                ("جذب و استخدام", "recruitment"),
            ]
        ]
        articles = []
        for i, (title, kind, extra) in enumerate(
            [
                ("چرا ارزیابی‌های سالانه شکست می‌خورند؟", ArticleKind.ARTICLE, {}),
                ("۵ اشتباه رایج در مصاحبه استخدامی", ArticleKind.ARTICLE, {}),
                ("مدیر خوب، کارمند خوب را نگه می‌دارد", ArticleKind.ARTICLE, {}),
                ("گفت‌وگوی بازخورد را چطور شروع کنیم؟", ArticleKind.ARTICLE, {}),
                (
                    "قسمت اول: منابع انسانی در سازمان‌های کوچک",
                    ArticleKind.PODCAST,
                    {
                        "audio_url": "https://example.com/podcast/episode-1.mp3",
                        "duration": "32:10",
                        "episode_number": 1,
                    },
                ),
                (
                    "ویدئو: طراحی شرح شغل در ۱۰ دقیقه",
                    ArticleKind.VIDEO,
                    {"video_url": "https://www.aparat.com/v/demo123"},
                ),
            ]
        ):
            article = ArticlePage(
                title=title,
                slug=f"post-{i + 1}",
                kind=kind,
                category=categories[i % 3],
                cover_image=images[(i + 2) % len(images)],
                intro=LOREM[:180],
                body=[
                    ("paragraph", p(LOREM)),
                    ("heading", "نکته کلیدی"),
                    ("paragraph", p(LOREM)),
                    (
                        "quote",
                        {
                            "text": "افراد مهم‌ترین دارایی نیستند؛ افراد مناسب هستند.",
                            "author": "جیم کالینز",
                        },
                    ),
                ],
                **extra,
            )
            publish(blog, article)
            article.tags.add("منابع انسانی", ["مدیریت", "سازمان", "استخدام"][i % 3])
            article.save_revision().publish()
            articles.append(article)
        Comment.objects.create(
            page=articles[0],
            name="علی",
            text="مطلب مفیدی بود، ممنون.",
            status=Comment.Status.APPROVED,
            ip_hash="demo",
        )
        Comment.objects.create(
            page=articles[0],
            name="نرگس",
            text="در سازمان ما هم همین مشکل را داشتیم.",
            status=Comment.Status.APPROVED,
            ip_hash="demo",
        )
        Comment.objects.create(
            page=articles[1], name="کاربر", text="این نظر هنوز تأیید نشده است.", ip_hash="demo"
        )

        portfolio = publish(
            home,
            PortfolioPage(
                title="نمونه‌کارها",
                slug="portfolio",
                intro=p("پروژه‌ها و سازمان‌هایی که با آن‌ها همکاری داشته‌ام."),
            ),
        )
        contact = publish(
            home,
            ContactPage(
                title="تماس",
                slug="contact",
                intro=p("برای هماهنگی جلسه یا پرسش، از راه‌های زیر با من در تماس باشید."),
            ),
        )
        consultation = publish(
            home,
            ConsultationPage(
                title="درخواست مشاوره",
                slug="consultation",
                intro=p("چند سؤال کوتاه تا بهتر بتوانم کمکتان کنم. کمتر از دو دقیقه وقت می‌گیرد."),
                show_in_menus=False,
            ),
        )
        booking_page = publish(
            home,
            BookingPage(
                title="رزرو جلسه",
                slug="booking",
                intro=p("نوع جلسه را انتخاب کنید، زمان مناسب را بردارید و پرداخت کنید."),
            ),
        )
        for i, (title, mode, minutes, price) in enumerate(
            [
                ("جلسه مشاوره آنلاین", SessionType.Mode.ONLINE, 60, 25_000_000),
                ("جلسه مشاوره حضوری", SessionType.Mode.IN_PERSON, 90, 40_000_000),
                ("گفت‌وگوی تلفنی کوتاه", SessionType.Mode.PHONE, 20, 0),
            ]
        ):
            SessionType.objects.create(
                title=title,
                description="این متن نمونه است و از پنل مدیریت قابل تغییر است.",
                mode=mode,
                duration_min=minutes,
                price=price,
                buffer_min=15,
                meeting_link="https://example.com/room" if mode == "online" else "",
                sort_order=i,
            )
        for weekday in Availability.Weekday.values[:5]:  # Saturday to Wednesday
            Availability.objects.create(
                weekday=weekday, start_time=dt.time(9, 0), end_time=dt.time(13, 0)
            )
            Availability.objects.create(
                weekday=weekday, start_time=dt.time(14, 0), end_time=dt.time(17, 0)
            )

        publish(
            home,
            LegalPage(title="قوانین و مقررات", slug="terms", body=p(LOREM), show_in_menus=False),
        )
        publish(
            home, LegalPage(title="حریم خصوصی", slug="privacy", body=p(LOREM), show_in_menus=False)
        )

        TeamMember.objects.create(name="عضو نمونه تیم", role="کارشناس", is_active=True)

        # --- home sections (spec section 10 order) -------------------------
        home.body = [
            (
                "hero",
                {
                    "title": "منابع انسانی را به مزیت رقابتی سازمانتان تبدیل کنید",
                    "subtitle": "مشاوره، آموزش و همراهی در ارزیابی عملکرد، ساختار سازمانی و جذب استعدادها.",
                    "image": portrait,
                    "buttons": [
                        {
                            "label": "درخواست مشاوره",
                            "page": consultation,
                            "url": "",
                            "style": "primary",
                        },
                        {
                            "label": "آشنایی با خدمات",
                            "page": services_index,
                            "url": "",
                            "style": "secondary",
                        },
                    ],
                },
            ),
            ("client_logos", {"title": "سازمان‌هایی که با آن‌ها کار کرده‌ام"}),
            (
                "services",
                {"title": "خدمات", "intro": "از تشخیص مسئله تا استقرار راه‌حل.", "services": []},
            ),
            (
                "stats",
                {
                    "title": "",
                    "items": [
                        {"value": "۱۵+", "label": "سال تجربه"},
                        {"value": "۶۰+", "label": "سازمان"},
                        {"value": "۳٬۰۰۰+", "label": "ساعت آموزش"},
                        {"value": "۵٬۰۰۰+", "label": "شرکت‌کننده"},
                    ],
                },
            ),
            ("testimonials", {"title": "نظر مشتریان", "testimonials": []}),
            ("latest_articles", {"title": "از مجله", "count": 3}),
            (
                "callback_form",
                {
                    "title": "با من تماس بگیرید",
                    "text": "نام و شماره‌تان را بگذارید؛ در اولین فرصت تماس می‌گیرم.",
                },
            ),
            (
                "cta",
                {
                    "title": "آماده‌اید شروع کنیم؟",
                    "text": "یک جلسه کوتاه برای شناخت نیاز سازمان شما.",
                    "buttons": [
                        {
                            "label": "درخواست مشاوره",
                            "page": consultation,
                            "url": "",
                            "style": "primary",
                        },
                    ],
                },
            ),
        ]
        home.save_revision().publish()

        # --- site settings --------------------------------------------------
        site = Site.objects.get(is_default_site=True)
        settings = SiteSettings.for_site(site)
        settings.brand_name = "Arezoo"
        settings.tagline = "مشاور منابع انسانی"
        settings.phone = "021 1234 5678"
        settings.email = "info@example.com"
        settings.address = "تهران، نمونه آدرس"
        settings.working_hours = "شنبه تا چهارشنبه، ۹ تا ۱۷"
        settings.whatsapp_number = "09120000000"
        settings.linkedin_url = "https://www.linkedin.com/"
        settings.instagram_url = "https://www.instagram.com/"
        settings.telegram_url = "https://t.me/"
        settings.footer_text = "مشاوره و آموزش منابع انسانی برای سازمان‌ها و افراد."
        settings.cta_label = "درخواست مشاوره"
        settings.cta_page = consultation
        settings.default_og_image = images[0]
        settings.main_menu = [
            ("link", {"label": label, "page": page, "url": ""})
            for label, page in [
                ("خانه", home),
                ("درباره من", about),
                ("خدمات", services_index),
                ("رزرو جلسه", booking_page),
                ("مجله", blog),
                ("نمونه‌کارها", portfolio),
                ("تماس", contact),
            ]
        ]
        settings.save()

        self.stdout.write(
            self.style.SUCCESS(f"Sample content created: {Page.objects.count() - 1} pages.")
        )

    def _reset(self, home):
        for model in (Payment, Booking, Order, Availability, SessionType):
            model.objects.all().delete()
        # Queryset delete lets treebeard keep the tree counters (numchild) consistent
        home.get_children().delete()
        # Reload before saving: the in-memory `home` still holds the old child count,
        # and saving it would write that stale count back and corrupt the tree
        home = HomePage.objects.get(pk=home.pk)
        for model in (Comment, Category, TeamMember, Testimonial, Project, Client):
            model.objects.all().delete()
        get_image_model().objects.filter(title__endswith=DEMO_TAG).delete()
        get_document_model().objects.filter(title__endswith=DEMO_TAG).delete()
        home.body = []
        home.save_revision().publish()
        self.stdout.write("Previous sample content removed.")
        return home
