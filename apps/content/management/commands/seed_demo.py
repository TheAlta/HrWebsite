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
from django.utils import timezone
from PIL import Image as PILImage
from PIL import ImageDraw
from wagtail.documents import get_document_model
from wagtail.images import get_image_model
from wagtail.models import Page, Site
from wagtail.rich_text import RichText

from apps.accounts.models import Organization
from apps.billing.models import Invoice, ProForma
from apps.booking.models import Availability, Booking, BookingPage, SessionType
from apps.certificates.models import Certificate
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
from apps.events.models import EventIndexPage, EventPage, Registration, SpeakingPage
from apps.orders.models import Order, Refund
from apps.payments.models import Payment
from apps.portfolio.models import Client, PortfolioPage, Project, Testimonial
from apps.shop.models import Coupon, CouponUse, DownloadToken, Product, Shipment, ShopPage

DEMO_TAG = "[demo]"  # marks sample images/documents so --reset can remove them

# The site's own colours (frontend/main.css), so sample pictures sit well in the design
PALETTE = [
    ("#14213d", "#2e4a7d"),
    ("#1d3461", "#a9c1f0"),
    ("#2e4a7d", "#c8a048"),
    ("#5a3a1c", "#c8a048"),
]


def make_image(title, size=(1200, 800), seed=0):
    """A simple generated picture (gradient + circles) — no network or stock photos needed."""
    rnd = random.Random(seed)  # noqa: S311 — sample pictures, not secrets
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
    draw.rectangle([120, 72, 240, 82], fill="#a39aa3")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return get_image_model().objects.create(
        title=f"لوگو {name} {DEMO_TAG}", file=ImageFile(buffer, name=f"logo-{seed}.png")
    )


def make_pdf(title):
    img = PILImage.new("RGB", (595, 842), "white")
    ImageDraw.Draw(img).rectangle([40, 40, 555, 120], fill="#4f4462")
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
        for i, (title, audience, summary, price, icon) in enumerate(
            [
                (
                    "ارزیابی عملکرد",
                    Audience.CORPORATE,
                    "طراحی و استقرار نظام ارزیابی عملکرد منصفانه و قابل اجرا.",
                    None,
                    "gauge",
                ),
                (
                    "طراحی ساختار سازمانی",
                    Audience.CORPORATE,
                    "چارت، شرح شغل و جریان تصمیم‌گیری متناسب با استراتژی.",
                    None,
                    "network",
                ),
                (
                    "جذب و استخدام",
                    Audience.CORPORATE,
                    "فرایند جذب از شرح شغل تا مصاحبه ساختاریافته.",
                    None,
                    "shield",
                ),
                (
                    "مشاوره مسیر شغلی",
                    Audience.INDIVIDUAL,
                    "جلسه فردی برای انتخاب مسیر، رزومه و آمادگی مصاحبه.",
                    25_000_000,
                    "route",
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
                        icon=icon,
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
        corporate = publish(
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

        events_page = publish(
            home,
            EventIndexPage(
                title="آموزش و رویدادها",
                slug="events",
                intro=p("دوره‌ها و وبینارهای پیش‌رو. این متن نمونه است."),
            ),
        )
        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        for i, (title, kind, days, price, capacity) in enumerate(
            [
                ("دوره ارزیابی عملکرد", EventPage.Kind.COURSE, 12, 80_000_000, 12),
                ("وبینار طراحی ساختار سازمانی", EventPage.Kind.WEBINAR, 5, 0, None),
                ("دوره جذب و مصاحبه", EventPage.Kind.COURSE, 30, 60_000_000, 1),
                ("وبینار مسیر شغلی", EventPage.Kind.WEBINAR, -20, 15_000_000, 50),
                ("سخنرانی همایش منابع انسانی", EventPage.Kind.TALK, -60, 0, None),
            ]
        ):
            start = now + dt.timedelta(days=days)
            publish(
                events_page,
                EventPage(
                    title=title,
                    slug=f"event-{i + 1}",
                    kind=kind,
                    summary="این متن نمونه است و از پنل مدیریت قابل تغییر است.",
                    body=p(LOREM),
                    instructor="مدرس نمونه",
                    venue="تهران، سالن نمونه" if kind == EventPage.Kind.TALK else "",
                    start_at=start,
                    end_at=start + dt.timedelta(hours=2),
                    capacity=capacity,
                    price=price,
                    join_link="https://example.com/room",
                ),
            )
        speaking = publish(
            home,
            SpeakingPage(
                title="سخنرانی‌ها",
                slug="speaking",
                intro=p("سوابق سخنرانی و فرم دعوت. این متن نمونه است."),
            ),
        )

        shop_page = publish(
            home,
            ShopPage(
                title="کتاب‌ها و محصولات",
                slug="shop",
                intro=p("کتاب چاپی و فایل آموزشی. این متن نمونه است."),
            ),
        )
        for i, (title, kind, price, stock) in enumerate(
            [
                ("کتاب مبانی منابع انسانی", Product.Kind.PHYSICAL, 3_500_000, 20),
                ("کتاب ارزیابی عملکرد", Product.Kind.PHYSICAL, 4_200_000, 0),
                ("راهنمای مصاحبه (PDF)", Product.Kind.DIGITAL, 1_500_000, 0),
            ]
        ):
            Product.objects.create(
                title=title,
                slug=f"product-{i + 1}",
                kind=kind,
                # No cover, so the drawn book cover shows (REPORT #058)
                summary="این متن نمونه است و از پنل مدیریت قابل تغییر است.",
                description=p(LOREM),
                contents=p("فصل اول، فصل دوم، فصل سوم"),
                price=price,
                stock=stock,
                file=SimpleUploadedFile("sample.pdf", b"%PDF-1.4 sample")
                if kind == Product.Kind.DIGITAL
                else "",
                sort_order=i,
            )
        Coupon.objects.create(code="DEMO10", type=Coupon.Type.PERCENT, value=10)

        publish(
            home,
            LegalPage(title="قوانین و مقررات", slug="terms", body=p(LOREM), show_in_menus=False),
        )
        publish(
            home, LegalPage(title="حریم خصوصی", slug="privacy", body=p(LOREM), show_in_menus=False)
        )

        TeamMember.objects.create(name="عضو نمونه تیم", role="کارشناس", is_active=True)

        # --- home sections, in the order of the owner's second demo (REPORT #058) ---
        home.body = [
            (
                "hero",
                {
                    "eyebrow": "مشاور منابع انسانی، مدرس و نویسنده",
                    "title": "سازمانی بسازید که آدم‌ها در آن رشد کنند…",
                    "highlight": "آدم‌ها",
                    "quote": "…بی‌آنکه خودتان در شلوغی‌اش گم شوید.",
                    "subtitle": (
                        "سال‌هاست کنار مدیرها و تیم‌های منابع انسانی کار می‌کنم تا استخدام،"
                        " ارزیابی و رشد آدم‌ها ساده‌تر، منصفانه‌تر و انسانی‌تر شود."
                    ),
                    "buttons": [
                        {
                            "label": "درخواست مشاورهٔ سازمانی",
                            "page": consultation,
                            "url": "",
                            "style": "primary",
                        },
                        {
                            "label": "رزرو جلسهٔ فردی",
                            "page": booking_page,
                            "url": "",
                            "style": "secondary",
                        },
                    ],
                    "image": None,
                    "photo_caption": "روی صحنه، در حال سخنرانی",
                    "sticker": "سلام!",
                    "badge_text": "سال‌ها تجربه ✳ مشاور منابع انسانی ✳ مدرس ✳ نویسنده ✳",
                },
            ),
            ("client_logos", {"title": "همکاری با"}),
            (
                "intro",
                {
                    "title": "سلام، من آرزو هستم.",
                    "highlight": "آرزو",
                    "text": RichText(
                        "<p>کمک می‌کنم سازمان‌ها <b>آدم‌محور</b> بمانند، مدیرها <b>بازخورد خوب</b>"
                        " بدهند و کارجوها تصمیم شغلی بعدی‌شان را آگاهانه بگیرند. از کجا شروع کنیم؟</p>"
                    ),
                    "paths": [
                        {
                            "label": "مدیر سازمانم",
                            "note": "مشاورهٔ سازمانی",
                            "page": consultation,
                            "url": "",
                        },
                        {
                            "label": "در تیم منابع انسانی کار می‌کنم",
                            "note": "دوره‌ها",
                            "page": events_page,
                            "url": "",
                        },
                        {
                            "label": "دنبال مسیر شغلی‌ام",
                            "note": "جلسهٔ فردی",
                            "page": booking_page,
                            "url": "",
                        },
                    ],
                },
            ),
            (
                "quiz",
                {
                    "eyebrow": "آماده‌اید برای",
                    "big": "سطح بعدی؟",
                    "title": "منابع انسانی سازمان شما در کدام مرحله است؟",
                    "text": "پنج سؤال، دو دقیقه. در پایان می‌گویم بیشترین اثر را کدام قدم دارد.",
                    "button_label": "کنجکاوید؟ آزمون را شروع کنید",
                    "questions": [
                        {"question": question, "answers": answers}
                        for question, answers in [
                            (
                                "وقتی نیروی جدید لازم دارید، استخدام چطور پیش می‌رود؟",
                                [
                                    "هر بار یک‌جور؛ آگهی و گپ آزاد",
                                    "فرم مصاحبه داریم، ولی همه از آن استفاده نمی‌کنند",
                                    "شایستگی‌ها تعریف شده و مصاحبه ساختاریافته است",
                                ],
                            ),
                            (
                                "ارزیابی عملکرد در سازمان شما…",
                                [
                                    "نداریم یا فقط روی کاغذ است",
                                    "سالی یک بار فرمی پر می‌شود",
                                    "چرخهٔ منظم دارد و به جلسهٔ بازخورد ختم می‌شود",
                                ],
                            ),
                            (
                                "شرح وظایف نقش‌ها…",
                                ["مکتوب نیست", "هست، ولی قدیمی است", "به‌روز و روشن است"],
                            ),
                            (
                                "آموزش کارکنان…",
                                [
                                    "پراکنده و موردی",
                                    "تقویم آموزشی داریم",
                                    "بر اساس نیازسنجی است و اثرش را می‌سنجیم",
                                ],
                            ),
                            (
                                "وقتی کسی استعفا می‌دهد…",
                                [
                                    "واقعاً نمی‌دانیم چرا رفت",
                                    "حدس‌هایی داریم",
                                    "مصاحبهٔ خروج داریم و داده‌اش را مرور می‌کنیم",
                                ],
                            ),
                        ]
                    ],
                    "results": [
                        {
                            "up_to": 3,
                            "name": "مرحلهٔ بنیان",
                            "text": (
                                "سازمان شما با انرژی آدم‌ها جلو می‌رود، نه با سیستم."
                                " اولین قدم: روشن کردن نقش‌ها و یک فرایند استخدام ساده."
                            ),
                            "service": services[1],
                            "topic": "structure",
                        },
                        {
                            "up_to": 7,
                            "name": "مرحلهٔ نظم‌دهی",
                            "text": (
                                "پایه‌ها را دارید ولی یکدست اجرا نمی‌شوند. بیشترین اثر را"
                                " یک نظام ارزیابی عملکرد گفت‌وگومحور می‌گذارد."
                            ),
                            "service": services[0],
                            "topic": "performance",
                        },
                        {
                            "up_to": 10,
                            "name": "مرحلهٔ رشد",
                            "text": (
                                "منابع انسانی شما بالغ است. وقت آن است که آن را به استراتژی"
                                " کسب‌وکار وصل کنید و رهبران آینده را بسازید."
                            ),
                            "service": None,
                            "topic": "training",
                        },
                    ],
                },
            ),
            (
                "free_resources",
                {
                    "eyebrow": "هدیه‌ای از من",
                    "title": "منابع رایگان",
                    "intro": "قالب‌ها و چک‌لیست‌هایی که در پروژه‌ها واقعاً استفاده می‌کنم.",
                    "topics": [
                        {"label": "جذب و استخدام", "icon": "shield"},
                        {"label": "ارزیابی عملکرد", "icon": "gauge"},
                        {"label": "رهبری تیم", "icon": "spark"},
                        {"label": "مسیر شغلی", "icon": "compass"},
                    ],
                    "resources": [
                        {
                            "topic": topic,
                            "title": title,
                            "format": fmt,
                            "document": make_pdf(title),
                            "button_label": "دانلود رایگان",
                        }
                        for topic, title, fmt in [
                            ("جذب و استخدام", "چک‌لیست مصاحبهٔ ساختاریافته", "PDF · ۶ صفحه"),
                            ("ارزیابی عملکرد", "قالب فرم ارزیابی عملکرد", "PDF · ۳ صفحه"),
                            ("رهبری تیم", "۲۰ سؤال برای جلسهٔ بازخورد", "PDF · ۳ صفحه"),
                            ("مسیر شغلی", "کاربرگ «تصمیم شغلی بعدی»", "PDF · ۴ صفحه"),
                        ]
                    ],
                },
            ),
            (
                "stats",
                {
                    "title": "",
                    "items": [
                        {"value": "۱۵+", "label": "سال تجربه در منابع انسانی"},
                        {"value": "۶۰+", "label": "سازمان همکار"},
                        {"value": "۳٬۰۰۰+", "label": "ساعت آموزش سازمانی"},
                        {"value": "۵٬۰۰۰+", "label": "شرکت‌کننده در دوره‌ها"},
                    ],
                },
            ),
            ("podcast", {"eyebrow": "پادکست هفتگی", "title": "گوش کنید، در راه کار", "count": 4}),
            (
                "latest_articles",
                {
                    "eyebrow": "نه یک",
                    "title": "وبلاگ",
                    "tagline": "معمولی منابع انسانی",
                    "intro": "یادداشت‌های کوتاه و کاربردی، بدون اصطلاحات قلمبه.",
                    "count": 3,
                },
            ),
            (
                "upcoming_event",
                {"title": "رویداد پیش رو", "button_label": "بله! جای من را نگه دار"},
            ),
            (
                "featured_book",
                {
                    "eyebrow": "کتاب تازه",
                    "product": str(Product.objects.order_by("pk").first().pk),
                    "second": str(Product.objects.filter(kind=Product.Kind.DIGITAL).first().pk),
                    "text": "این متن نمونه است و از پنل مدیریت قابل تغییر است.",
                    "badge": "پرفروش",
                    "quote": "کتابی که دوست داشتم روز اول مدیریتم داشته باشم.",
                    "quote_by": "یک خوانندهٔ کتاب",
                },
            ),
            (
                "library",
                {
                    "eyebrow": "کتابخانهٔ آموزشی",
                    "title": "یاد بگیرید، با سرعت خودتان",
                    "items": [
                        {
                            "kind": kind,
                            "title": title,
                            "meta": meta,
                            "link": {"label": title, "page": target, "url": ""},
                        }
                        for kind, title, meta, target in [
                            ("دوره", "طراحی نظام ارزیابی عملکرد", "۴ جلسه · آنلاین", events_page),
                            ("وبینار رایگان", "اشتباه‌های رایج مصاحبه", "۷۵ دقیقه", events_page),
                            ("بستهٔ آموزشی", "قالب‌های ارزیابی عملکرد", "فایل دیجیتال", shop_page),
                            ("کوچینگ", "از متخصص خوب به مدیر خوب", "جلسهٔ فردی", booking_page),
                        ]
                    ],
                },
            ),
            (
                "testimonials",
                {"eyebrow": "از زبان خودشان", "title": "همکاران چه می‌گویند", "testimonials": []},
            ),
            (
                "newsletter",
                {
                    "title": "نامه‌ای کوتاه، هر دو هفته یک بار",
                    "text": (
                        "یک ایده، یک قالب و یک سؤال برای جلسهٔ بعدی تیم‌تان."
                        " بدون تبلیغ؛ هر وقت خواستید لغو کنید."
                    ),
                    "badge_text": "خبرنامه‌ای واقعی ✳ برای صندوق شما ✳ هر دو هفته ✳",
                },
            ),
            (
                "contact_band",
                {
                    "callback_title": "پروژهٔ سازمانی دارید؟",
                    "callback_text": (
                        "نام و شماره‌تان را بگذارید؛ برای یک گفت‌وگوی ۲۰ دقیقه‌ای"
                        " و بدون هزینه تماس می‌گیرم."
                    ),
                    "document": resume,
                    "document_title": "دریافت رزومهٔ کامل",
                    "document_text": "رزومه و فهرست پروژه‌ها را دریافت کنید.",
                },
            ),
        ]
        home.save_revision().publish()

        # --- site settings --------------------------------------------------
        site = Site.objects.get(is_default_site=True)
        settings = SiteSettings.for_site(site)
        settings.brand_name = "آرزو زحمت‌بران"
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
        settings.shipping_fee = 500_000
        settings.seller_name = "فروشنده نمونه"
        settings.free_shipping_from = 10_000_000
        settings.cta_label = "درخواست مشاوره"
        settings.cta_page = consultation
        settings.default_og_image = images[0]

        def link(label, page, description="", icon=""):
            return {
                "label": label,
                "page": page,
                "url": "",
                "description": description,
                "icon": icon,
            }

        # The demo's menu: two dropdown groups (REPORT #055)
        settings.main_menu = [
            ("link", {"label": "خانه", "page": home, "url": ""}),
            ("link", {"label": "درباره من", "page": about, "url": ""}),
            (
                "group",
                {
                    "label": "خدمات",
                    "links": [
                        link("همهٔ خدمات", services_index, "خدمات فردی و سازمانی", "briefcase"),
                        link("خدمات سازمانی", corporate, "ساختار، جذب، ارزیابی و آموزش", "users"),
                        link(
                            "رزرو جلسهٔ مشاوره",
                            booking_page,
                            "انتخاب زمان و پرداخت آنلاین",
                            "calendar",
                        ),
                    ],
                },
            ),
            ("link", {"label": "آموزش و رویدادها", "page": events_page, "url": ""}),
            (
                "group",
                {
                    "label": "منابع",
                    "links": [
                        link("مجله", blog, "مقاله، پادکست و ویدئو", "newspaper"),
                        link("کتاب‌ها و محصولات", shop_page, "کتاب چاپی و فایل آموزشی", "book"),
                        link("نمونه‌کارها", portfolio, "پروژه‌ها و نظر مشتریان", "award"),
                        link("سخنرانی‌ها", speaking, "سوابق و دعوت به سخنرانی", "mic"),
                    ],
                },
            ),
            ("link", {"label": "تماس", "page": contact, "url": ""}),
        ]
        settings.save()

        self.stdout.write(
            self.style.SUCCESS(f"Sample content created: {Page.objects.count() - 1} pages.")
        )

    def _reset(self, home):
        # Invoices, pre-invoices and refunds protect their orders, and certificates
        # their registrations, so they go first
        for model in (
            Certificate,
            Invoice,
            ProForma,
            Refund,
            CouponUse,
            Coupon,
            DownloadToken,
            Shipment,
            Registration,
            Payment,
            Booking,
            Order,
            Organization,
            Product,
            Availability,
            SessionType,
        ):
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
