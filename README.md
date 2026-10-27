# HrWebsite — سایت مشاوره منابع انسانی

سایت شخصی مشاور منابع انسانی شامل معرفی، خدمات فردی و سازمانی، دوره‌ها و وبینارها، فروش کتاب و محصولات آموزشی، رزرو جلسه، پرداخت اینترنتی، CRM سرنخ‌ها و اطلاع‌رسانی پیامکی.

## اسناد

| فایل | محتوا |
|---|---|
| [`docs/spec.html`](docs/spec.html) | سند توسعه (مرجع نیازمندی‌ها و معماری) |
| [`docs/SPRINTS.md`](docs/SPRINTS.md) | اسپرینت‌بندی تأییدشده |
| [`CLAUDE.md`](CLAUDE.md) | قرارداد کاری و راهنمای توسعه |
| [`REPORT.md`](REPORT.md) | دفتر گزارش ترتیبی پروژه |

## استک

Python 3.12 · Django 5.2 LTS · Wagtail 8 · PostgreSQL 16 · HTMX · Alpine.js · Tailwind CSS 4 · Django-Q2 · Docker Compose

---

## راه‌اندازی محلی

**پیش‌نیاز:** Docker Desktop

```bash
cp .env.example .env        # فقط بار اول
docker compose up           # همه سرویس‌ها را بالا می‌آورد
```

بار اول ساخت ایمیج چند دقیقه طول می‌کشد. بعد از آن:

| آدرس | چیست |
|---|---|
| http://localhost:8100 | سایت |
| http://localhost:8100/panel/ | پنل مدیریت Wagtail |
| http://localhost:8100/healthz | وضعیت سلامت |
| http://localhost:8025 | Mailpit (ایمیل‌های ارسالی در محیط توسعه) |

**ساخت حساب مدیر** (یک بار):

```bash
docker compose exec web python manage.py createsuperuser
```

نام کاربری، شماره موبایل است (مثل `09121234567`).

**محتوای نمونه** (برای دیدن و تست همه صفحات):

```bash
docker compose exec web python manage.py seed_demo           # فقط وقتی سایت خالی است
docker compose exec web python manage.py seed_demo --reset   # پاک کردن و ساخت دوباره محتوای نمونه
```

**پیامک در محیط توسعه:** پیامک واقعی ارسال نمی‌شود و متن آن در لاگ می‌آید. کد ورود (OTP) را این‌طور ببینید:

```bash
docker compose logs worker | grep SMS
```

در پنل، بخش «پیام‌های ارسالی» همه پیام‌ها را نشان می‌دهد، ولی کد ورود بعد از ارسال در آنجا پوشانده می‌شود.

**راهنمای طراحی:** http://localhost:8100/styleguide/ همه اجزای مشترک را یک‌جا نشان می‌دهد (فقط در محیط توسعه).

### سرویس‌های محیط توسعه

| سرویس | کار |
|---|---|
| `db` | PostgreSQL 16 |
| `migrate` | اجرای migrationها؛ کارش که تمام شد خارج می‌شود |
| `web` | سرور توسعه Django |
| `worker` | اجرای کارهای پس‌زمینه (Django-Q2) |
| `css` | ساخت خودکار CSS با Tailwind هنگام تغییر قالب‌ها (با polling، چون رویداد تغییر فایل از ویندوز به کانتینر نمی‌رسد) |
| `mailpit` | گرفتن ایمیل‌های خروجی |

### دستورهای رایج

```bash
# تست‌ها و بررسی کد
docker compose run --rm -e DJANGO_SETTINGS_MODULE=config.settings.test web pytest
docker compose run --rm web ruff check .
docker compose run --rm web ruff format .

# migration جدید
docker compose run --rm web python manage.py makemigrations

# بعد از تغییر requirements/*.txt
docker compose build

# پاک کردن کامل داده‌های محلی (پایگاه داده هم پاک می‌شود)
docker compose down -v
```

### افزودن پکیج پایتون

1. پکیج را به `pyproject.toml` اضافه کنید.
2. فایل‌های قفل را دوباره بسازید (نسخه‌ها و hashها):

```bash
docker run --rm -v "$PWD:/app" -w /app python:3.12-slim sh -c "\
  pip install -q -i https://repo.hmirror.ir/python/simple uv==0.13.5 && \
  export UV_INDEX_URL=https://repo.hmirror.ir/python/simple && \
  uv pip compile pyproject.toml --python-version 3.12 --generate-hashes -o requirements/base.txt && \
  uv pip compile pyproject.toml --group dev --python-version 3.12 --generate-hashes -o requirements/dev.txt"
```

> **چرا میرور؟** دسترسی به `files.pythonhosted.org` (محل فایل‌های PyPI) از ایران فیلتر است. ایمیج‌ها به‌طور پیش‌فرض از میرور `repo.hmirror.ir` نصب می‌کنند و CI روی GitHub از PyPI اصلی. hashها در هر دو یکسان‌اند. جزئیات در `REPORT.md` ورودی #012.

### پورت‌ها

اگر پورت `8100` یا `8025` روی سیستم شما اشغال است، در `.env` مقدار `WEB_PORT` یا `MAILPIT_PORT` را عوض کنید.

## ساختار پروژه

```
config/           تنظیمات (base, dev, test, prod) و URLها
apps/
  core/           ابزارهای مشترک: تاریخ شمسی، پول، متن فارسی، فیلد موبایل، ویدئو، healthz
  accounts/       کاربر با ورود موبایلی
  content/        صفحات Wagtail، مجله، نظرها، تنظیمات سایت، سئو
  portfolio/      مشتریان، نظر مشتریان، پروژه‌ها
  crm/            فرم‌های سرنخ، CRM در پنل، یادآور پیگیری
  notifications/  پیامک و ایمیل، آداپتر کاوه‌نگار، لاگ پیام‌ها
templates/        قالب‌های HTML
  components/     اجزای مشترک (کارت، دکمه، فیلد، ...) — ظاهر از اینجا و توکن‌ها عوض می‌شود
  blocks/         بلوک‌های قابل چیدن از پنل
  includes/       هدر، فوتر، متای سئو
frontend/         ورودی Tailwind (فقط زمان ساخت)
static/           فایل‌های عمومی: فونت، کتابخانه‌های JS، CSS ساخته‌شده
requirements/     فایل‌های قفل وابستگی‌ها با hash
```
