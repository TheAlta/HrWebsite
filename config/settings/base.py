"""Settings shared by every environment. Environment-specific files override these."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    # Project apps
    "apps.core",
    "apps.accounts",
    "apps.content",
    "apps.portfolio",
    "apps.notifications",
    "apps.crm",
    "apps.orders",
    "apps.payments",
    "apps.booking",
    "apps.events",
    "apps.shop",
    # Wagtail
    "wagtail.contrib.settings",
    "wagtail.contrib.sitemaps",
    "wagtail.contrib.routable_page",
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    "modelcluster",
    "taggit",
    # Third party
    "django_htmx",
    "django_q",
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "django.contrib.postgres",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "apps.core.middleware.UTMMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "wagtail.contrib.settings.context_processors.settings",
                "apps.core.context_processors.site",
                "apps.shop.context_processors.cart",
            ],
            "builtins": ["apps.core.templatetags.core_tags"],
        },
    },
]

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Auth — users log in with their mobile number (see apps.accounts)
AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Language and time: Persian UI; times stored in UTC, displayed in Tehran time
LANGUAGE_CODE = "fa"
LANGUAGES = [("fa", "فارسی")]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
TIME_ZONE = "Asia/Tehran"
USE_TZ = True

# Static and media files
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    # Paid files (SHOP-2): outside MEDIA_ROOT, so no URL reaches them directly
    "private": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": BASE_DIR / "private", "base_url": None},
    },
}

# Email
EMAIL_CONFIG = env.email_url("EMAIL_URL", default="consolemail://")
vars().update(EMAIL_CONFIG)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@localhost")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Login (OTP, sprint 2)
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:account"

# SMS (NTF-1). Development logs messages; production sets the Kavenegar provider.
SMS_PROVIDER = env("SMS_PROVIDER", default="apps.notifications.providers.console.ConsoleSMS")
KAVENEGAR_API_KEY = env("KAVENEGAR_API_KEY", default="")
# Template names as approved in the SMS panel; keys are used in code
SMS_TEMPLATES = {
    "otp": env("SMS_TPL_OTP", default="otp"),
    "lead_received": env("SMS_TPL_LEAD_RECEIVED", default="lead-received"),
    "lead_admin": env("SMS_TPL_LEAD_ADMIN", default="lead-admin"),
    "booking_confirmed": env("SMS_TPL_BOOKING_CONFIRMED", default="booking-confirmed"),
    "booking_reminder": env("SMS_TPL_BOOKING_REMINDER", default="booking-reminder"),
    "booking_cancelled": env("SMS_TPL_BOOKING_CANCELLED", default="booking-cancelled"),
    "booking_problem": env("SMS_TPL_BOOKING_PROBLEM", default="booking-problem"),
    "event_registered": env("SMS_TPL_EVENT_REGISTERED", default="event-registered"),
    "event_waitlisted": env("SMS_TPL_EVENT_WAITLISTED", default="event-waitlisted"),
    "event_seat_open": env("SMS_TPL_EVENT_SEAT_OPEN", default="event-seat-open"),
    "event_cancelled": env("SMS_TPL_EVENT_CANCELLED", default="event-cancelled"),
    "event_reminder": env("SMS_TPL_EVENT_REMINDER", default="event-reminder"),
    "event_recording": env("SMS_TPL_EVENT_RECORDING", default="event-recording"),
    "event_problem": env("SMS_TPL_EVENT_PROBLEM", default="event-problem"),
    "order_digital": env("SMS_TPL_ORDER_DIGITAL", default="order-digital"),
    "order_shipped": env("SMS_TPL_ORDER_SHIPPED", default="order-shipped"),
    "order_problem": env("SMS_TPL_ORDER_PROBLEM", default="order-problem"),
}
# Parameters of these templates are masked in the message log once sent
SMS_SENSITIVE_TEMPLATES = {"otp"}
# Alert when this many SMS go out within an hour (OTP abuse, REPORT #023)
SMS_ALERT_PER_HOUR = env.int("SMS_ALERT_PER_HOUR", default=50)
ALERT_EMAILS = env.list("ALERT_EMAILS", default=[])

# Payment (PAY-1). The order is primary then backup; `fake` is the local test bank
PAYMENT_GATEWAYS = {
    "zarinpal": "apps.payments.gateways.zarinpal.ZarinpalGateway",
    "zibal": "apps.payments.gateways.zibal.ZibalGateway",
    "fake": "apps.payments.gateways.fake.FakeGateway",
}
PAYMENT_GATEWAY_ORDER = env.list("PAYMENT_GATEWAY_ORDER", default=["fake"])
ZARINPAL_MERCHANT_ID = env("ZARINPAL_MERCHANT_ID", default="")
ZARINPAL_SANDBOX = env.bool("ZARINPAL_SANDBOX", default=False)
ZIBAL_MERCHANT = env("ZIBAL_MERCHANT", default="")

# seed_demo deletes and recreates pages; production keeps this off
ALLOW_SEED_DEMO = env.bool("ALLOW_SEED_DEMO", default=True)

# Behind Caddy in production (sprint 3) the client IP comes from X-Forwarded-For
TRUST_X_FORWARDED_FOR = env.bool("TRUST_X_FORWARDED_FOR", default=False)

# Background tasks (Django-Q2, queue stored in PostgreSQL — see REPORT #005)
Q_CLUSTER = {
    "name": "hrweb",
    "orm": "default",
    "workers": env.int("Q_WORKERS", default=2),
    "timeout": 120,
    "retry": 180,  # must be greater than timeout
    "max_attempts": 3,
    "catch_up": False,
}

# Wagtail
WAGTAIL_SITE_NAME = env("SITE_NAME", default="Arezoo")
WAGTAILADMIN_BASE_URL = env("WAGTAILADMIN_BASE_URL", default="http://localhost:8100")
WAGTAIL_ADMIN_PATH = env("WAGTAIL_ADMIN_PATH", default="panel/")
DJANGO_ADMIN_PATH = env("DJANGO_ADMIN_PATH", default="django-admin/")
# "simple": no English stemming/stop words, so Persian text is indexed as-is
WAGTAILSEARCH_BACKENDS = {
    "default": {"BACKEND": "wagtail.search.backends.database", "SEARCH_CONFIG": "simple"}
}
WAGTAILEMBEDS_RESPONSIVE_HTML = True
WAGTAILDOCS_EXTENSIONS = ["csv", "docx", "odt", "pdf", "pptx", "txt", "xlsx", "zip"]
WAGTAILIMAGES_FORMAT_CONVERSIONS = {"bmp": "webp", "png": "webp", "jpeg": "webp"}

# SEO: only production lets search engines index the site (robots.txt + meta robots)
SEO_ALLOW_INDEXING = env.bool("SEO_ALLOW_INDEXING", default=False)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
        "django_tasks": {"level": "WARNING"},
    },
}
