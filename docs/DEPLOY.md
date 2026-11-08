# راهنمای استقرار

این راهنما سایت را روی یک VPS بالا می‌آورد. همه دستورها روی سرور اجرا می‌شوند، مگر این‌که خلافش گفته شده باشد.

> **هاست اشتراکی کافی نیست.** سایت به Docker، PostgreSQL و یک برنامه همیشه‌روشن (worker) نیاز دارد (REPORT #035).

## ۱. پیش‌نیازها

| مورد | جزئیات |
|---|---|
| سرور | Ubuntu 24.04، حداقل ۲ هسته و ۴ گیگ رم برای شروع. پیشنهاد سند ۴ هسته، ۸ گیگ رم و ۸۰ گیگ SSD است. |
| دسترسی | root با کلید SSH |
| دامنه | `arezoo-zahmatbaran.ir` |
| پیامک | حساب کاوه‌نگار و الگوهای تأییدشده (بخش ۷) |
| درگاه | کد پذیرنده زرین‌پال یا زیبال. درگاه به اینماد نیاز دارد. |

## ۲. DNS

در پنل فعلی دامنه (DirectAdmin ← DNS Management) این رکوردها را روی IP سرور جدید بگذارید:

| نوع | نام | مقدار |
|---|---|---|
| A | `@` | IP سرور |
| A | `www` | IP سرور |
| A | `staging` | IP سرور |

اگر ایمیل دامنه روی همان هاست می‌ماند، رکوردهای `MX` و `mail` را تغییر ندهید.

## ۳. آماده‌سازی سرور

```bash
apt update && apt upgrade -y
apt install -y git curl ufw
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable

curl -fsSL https://get.docker.com | sh
```

اگر سرور داخل ایران است، Docker Hub در دسترس نیست. میرور را تنظیم کنید و سپس Docker را راه‌اندازی مجدد کنید:

```bash
cat > /etc/docker/daemon.json <<'EOF'
{ "registry-mirrors": ["https://docker.arvancloud.ir"] }
EOF
systemctl restart docker
docker pull hello-world   # باید بدون خطا تمام شود
```

ساخت پوشه‌ها. شناسه `1000` همان کاربری است که برنامه با آن اجرا می‌شود:

```bash
mkdir -p /srv/hrweb/{production,staging}/{media,private,postgres,backups} /srv/hrweb/caddy/{data,config}
chown -R 1000:1000 /srv/hrweb/{production,staging}/{media,private}
```

## ۴. کد و تنظیمات

```bash
cd /srv/hrweb
git clone https://github.com/TheAlta/HrWebsite.git app-production
git clone https://github.com/TheAlta/HrWebsite.git app-staging

cp app-production/deploy/env.example production/.env
cp app-production/deploy/env.example staging/.env
cp app-production/deploy/caddy.env.example caddy.env
chmod 600 production/.env staging/.env
```

هر دو فایل `.env` را پر کنید. تفاوت‌های Staging:

| تنظیم | Production | Staging |
|---|---|---|
| `WEB_PORT` | `8001` | `8002` |
| `DATA_DIR` | `/srv/hrweb/production` | `/srv/hrweb/staging` |
| دامنه‌ها | `arezoo-zahmatbaran.ir` | `staging.arezoo-zahmatbaran.ir` |
| `SEO_ALLOW_INDEXING` | `true` | `false` |
| `ZARINPAL_SANDBOX` | `false` | `true` |

رمز `POSTGRES_PASSWORD` باید با رمز داخل `DATABASE_URL` یکی باشد. در هر محیط مقدار جدا بگذارید.

## ۵. اولین استقرار

```bash
cd /srv/hrweb/app-staging && ./deploy/deploy.sh staging main
cd /srv/hrweb/app-production && ./deploy/deploy.sh production main

cd /srv/hrweb/app-production
docker compose -f compose.caddy.yml --env-file /srv/hrweb/caddy.env -p hrweb-caddy up -d
```

ساخت حساب مدیر (نام کاربری، شماره موبایل است):

```bash
docker exec -it hrweb-production-web-1 python manage.py createsuperuser
```

در پنل، این‌ها را تنظیم کنید:

نقش‌های پنل («مدیر کل»، «ویراستار محتوا»، «پشتیبان») بعد از هر migrate خودکار ساخته می‌شوند. برای هر کارمند در **Settings ← Users** یک کاربر بسازید و یکی از این گروه‌ها را به او بدهید. سرنخ‌ها و آمار فروش فقط برای «مدیر کل» دیده می‌شوند.

1. **Settings ← Sites:** نام میزبان را `arezoo-zahmatbaran.ir` و پورت را `443` بگذارید. آدرس canonical از این‌جا ساخته می‌شود.
2. **Settings ← تنظیمات سایت:** تماس، واتساپ، منو، ایمیل و موبایل اعلان‌ها.
3. **رزرو جلسه:** انواع جلسه، ساعات کاری، مرخصی‌ها.
4. **Settings ← تنظیمات سایت ← فاکتور:** نام حقیقی یا حقوقی، شناسه ملی، کد اقتصادی و نشانی فروشنده. این‌ها روی هر فاکتور تازه چاپ می‌شوند و فاکتورهای قبلی تغییر نمی‌کنند.

## ۶. بکاپ

```bash
openssl rand -base64 32 > /srv/hrweb/backup-passphrase
chmod 600 /srv/hrweb/backup-passphrase
crontab -e
```

```cron
30 2 * * * /srv/hrweb/app-production/deploy/backup.sh production >> /var/log/hrweb-backup.log 2>&1
```

> **یک نسخه از `backup-passphrase` را بیرون از سرور نگه دارید.** بدون آن هیچ بکاپی بازگردانی نمی‌شود.

برای کپی در مکان دوم (الزام سند، بخش ۱۱): `rclone` را تنظیم کنید و `BACKUP_RCLONE_REMOTE` را در crontab بگذارید.

**بازگردانی:**

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -pass file:/srv/hrweb/backup-passphrase \
  -in /srv/hrweb/production/backups/db-XXXX.sql.gz.enc | gunzip \
  | docker exec -i hrweb-production-db-1 psql -U hrweb hrweb
```

بازگردانی را ماهی یک بار روی Staging تست کنید.

## ۷. الگوهای پیامک

این الگوها را در پنل کاوه‌نگار ثبت کنید و نام تأییدشده را در `.env` بگذارید. در کاوه‌نگار، `token` تا `token3` فاصله نمی‌پذیرند و `token10` و `token20` می‌پذیرند.

| تنظیم | توکن‌ها | متن پیشنهادی |
|---|---|---|
| `SMS_TPL_OTP` | `token` | کد ورود شما: %token |
| `SMS_TPL_LEAD_RECEIVED` | `token10` | %token10 عزیز، درخواست شما ثبت شد. به‌زودی تماس می‌گیرم. |
| `SMS_TPL_LEAD_ADMIN` | `token`، `token10` | سرنخ جدید شماره %token: %token10 |
| `SMS_TPL_BOOKING_CONFIRMED` | `token`، `token10` | جلسه شما برای %token10 ثبت شد. شماره سفارش: %token |
| `SMS_TPL_BOOKING_REMINDER` | `token10`، `token20` | یادآوری جلسه: %token10. لینک: %token20 |
| `SMS_TPL_BOOKING_CANCELLED` | `token10` | جلسه %token10 لغو شد. |
| `SMS_TPL_BOOKING_PROBLEM` | `token10` | پرداخت شما ثبت شد ولی زمان %token10 آزاد نیست. به‌زودی تماس می‌گیرم. |
| `SMS_TPL_EVENT_REGISTERED` | `token`، `token10`، `token20` | ثبت‌نام شما در %token20 انجام شد. زمان: %token10. لینک ورود: %token |
| `SMS_TPL_EVENT_WAITLISTED` | `token20` | ظرفیت %token20 پر است و شما در لیست انتظار هستید. |
| `SMS_TPL_EVENT_SEAT_OPEN` | `token10`، `token20` | در %token20 جا باز شد. تا %token10 از حساب کاربری پرداخت کنید. |
| `SMS_TPL_EVENT_CANCELLED` | `token20` | ثبت‌نام شما در %token20 لغو شد. |
| `SMS_TPL_EVENT_REMINDER` | `token`، `token10`، `token20` | یادآوری %token20: %token10. لینک ورود: %token |
| `SMS_TPL_EVENT_RECORDING` | `token20` | ضبط %token20 در حساب کاربری شما آماده است. |
| `SMS_TPL_EVENT_PROBLEM` | `token20` | پرداخت شما برای %token20 ثبت شد ولی ظرفیت پر شده است. به‌زودی تماس می‌گیرم. |
| `SMS_TPL_ORDER_DIGITAL` | `token` | سفارش %token آماده است. فایل را از حساب کاربری دانلود کنید. |
| `SMS_TPL_ORDER_SHIPPED` | `token`، `token2` | سفارش %token ارسال شد. کد رهگیری: %token2 |
| `SMS_TPL_ORDER_PROBLEM` | `token` | پرداخت سفارش %token ثبت شد ولی موجودی تمام شده است. به‌زودی تماس می‌گیرم. |
| `SMS_TPL_ORDER_INVOICE` | `token` | فاکتور شماره %token صادر شد: arezoo-zahmatbaran.ir/account/invoices/%token/ |
| `SMS_TPL_ORDER_REFUNDED` | `token` | مبلغ سفارش %token به حساب شما برگردانده شد. |
| `SMS_TPL_PROFORMA_READY` | `token`، `token2` | پیش‌فاکتور %token صادر شد. مشاهده و پرداخت: arezoo-zahmatbaran.ir/orders/%token2/ |
| `SMS_TPL_CERTIFICATE_READY` | `token`، `token20` | گواهی حضور شما در %token20 صادر شد. کد استعلام: %token. دریافت از حساب کاربری: arezoo-zahmatbaran.ir/account/courses/ |
| `SMS_TPL_NEWSLETTER` | `token20` | %token20 arezoo-zahmatbaran.ir لغو۱۱ |

> **پیامک خبرنامه** تبلیغاتی است و کاوه‌نگار برای آن خط و الگوی جدا می‌خواهد. قبل از اولین ارسال پیامکی، شرایط پنل را بررسی کنید.

## ۸. انتشار نسخه جدید

```bash
# Staging، از آخرین main
cd /srv/hrweb/app-staging && ./deploy/deploy.sh staging main

# Production، فقط از روی تگ و بعد از تأیید مالک محصول
cd /srv/hrweb/app-production && ./deploy/deploy.sh production v1.0.0
```

اسکریپت بعد از بالا آمدن، `/healthz` را چک می‌کند و اگر خراب باشد لاگ را نشان می‌دهد.

**برگشت به نسخه قبل:** همان دستور با تگ قبلی.

```bash
./deploy/deploy.sh production v1.0.0
```

اگر نسخه جدید migration داشته، برگشت کد کافی نیست. قبل از هر انتشار، یک بکاپ دستی بگیرید.

## ۹. چک‌لیست بعد از انتشار

- [ ] `https://arezoo-zahmatbaran.ir/healthz` مقدار `{"status": "ok"}` می‌دهد و قفل HTTPS سبز است.
- [ ] `https://www...` به دامنه اصلی منتقل می‌شود.
- [ ] `robots.txt` روی Production باز و روی Staging بسته است.
- [ ] ورود با OTP با پیامک واقعی کار می‌کند.
- [ ] فرم مشاوره، ایمیل و پیامک اعلان را می‌فرستد.
- [ ] یک رزرو با پرداخت واقعی کم‌مبلغ انجام می‌شود و بعد مبلغ برگردانده می‌شود.
- [ ] `docker logs hrweb-production-worker-1` خطا ندارد.
- [ ] بکاپ شبانه ساخته می‌شود و یک بار بازگردانی تست شده است.

## ۱۰. موارد الزامی قبل از باز شدن عمومی سایت

ورود دومرحله‌ای، محدودیت تلاش ورود و هدرهای CSP در اسپرینت ۶ ساخته شدند و روی سرور خودبه‌خود روشن‌اند (REPORT #051). این‌ها در اسپرینت D می‌مانند:

- [ ] یک آدرس سخت‌حدس برای `WAGTAIL_ADMIN_PATH` و `DJANGO_ADMIN_PATH` در `.env`
- [ ] اولین ورود هر کارمند به پنل: نصب اپ Authenticator، اسکن QR، و نگه‌داشتن ۱۰ کد پشتیبان در جای امن
- [ ] تست پرداخت واقعی با زرین‌پال و زیبال

### ورود دومرحله‌ای و قفل ورود پنل

- **همه کسانی که پنل را باز می‌کنند** (مدیر کل، ویراستار، پشتیبان) یک بار اپ Google Authenticator یا Microsoft Authenticator را راه می‌اندازند. بعد از آن در هر ورود، کد ۶ رقمی اپ لازم است. مشتری‌ها هیچ تغییری نمی‌بینند.
- **ساعت گوشی** باید روی تنظیم خودکار باشد، چون کد اپ به ساعت وابسته است.
- **گوشی گم شد:** با یکی از کدهای پشتیبان وارد شوید. اگر کدها هم در دسترس نیستند:
  ```bash
  docker exec -it hrweb-production-web-1 python manage.py reset_two_factor 0912xxxxxxx
  ```
  در ورود بعدی، اپ از اول راه‌اندازی می‌شود.
- **ورود قفل شد:** بعد از ۵ رمز اشتباه پشت سر هم برای یک نام کاربری از یک آدرس، ورود ۳۰ دقیقه بسته می‌شود. صبر کنید، یا:
  ```bash
  docker exec -it hrweb-production-web-1 python manage.py axes_reset_username 0912xxxxxxx
  ```
- `PANEL_2FA_REQUIRED` و `AXES_ENABLED` روی سرور نباید `false` شوند. فقط روی سیستم محلی ورود دومرحله‌ای پیش‌فرض خاموش است.

## ۱۱. ویژگی‌های خاموش و روشن کردنشان

این ویژگی‌ها به سرویس بیرونی وابسته‌اند و پیش‌فرض خاموش‌اند (REPORT #051). روشن کردن هر کدام یک خط در `.env` است. قبل از روشن کردن، فرمان بررسی را اجرا کنید.

### تقویم شخصی (`BOOK-6`)

قرارهای شخصی تقویم شما زمان‌های رزرو را می‌بندند. سرور هر ۱۰ دقیقه تقویم را می‌خواند. فقط زمان شروع و پایان ذخیره می‌شود و عنوان قرارها نه.

1. در تقویم گوگل، از تنظیمات تقویم موردنظر بخش «Integrate calendar» را باز کنید و «Secret address in iCal format» را کپی کنید. Outlook و تقویم اپل هم آدرس iCal مشابهی دارند.
2. آدرس را در `.env` بگذارید. چند تقویم را با ویرگول جدا کنید:
   ```
   BUSY_CALENDAR_URLS=https://calendar.google.com/calendar/ical/.../basic.ics
   ```
3. بررسی کنید. فرمان چیزی ذخیره نمی‌کند و فقط می‌گوید چند زمان اشغال خوانده شد یا مشکل کجاست:
   ```bash
   docker exec -it hrweb-production-web-1 python manage.py check_calendar
   ```
4. سایت را دوباره راه بیندازید (`./deploy/deploy.sh production <تگ فعلی>`).

- **این آدرس رمز است.** هر کس آن را داشته باشد عنوان و زمان قرارهایتان را می‌بیند. فقط در `.env` بماند. اگر فکر می‌کنید لو رفته، در همان بخش تنظیمات گوگل «Reset» را بزنید و آدرس تازه را جایگزین کنید.
- **اگر خواندن قطع شود:** رزرو با آخرین زمان‌های خوانده‌شده ادامه پیدا می‌کند. بعد از نیم ساعت خطای پشت سر هم، یک ایمیل هشدار به ایمیل اعلان پنل می‌رسد.
- **قرار «آزاد»:** قرارهایی که در تقویم «Free» یا «آزاد» علامت خورده‌اند، زمان را نمی‌بندند. رویدادهای تمام‌روز گوگل پیش‌فرض «آزاد» هستند. اگر می‌خواهید یک روز کامل بسته شود، آن را «Busy» کنید.
- **خاموش کردن:** `BUSY_CALENDAR_URLS` را خالی کنید و سایت را دوباره راه بیندازید. حداکثر ۱۰ دقیقه بعد، زمان‌هایی که از تقویم کپی شده بودند هم پاک می‌شوند.

### اتاق کلاس آنلاین (زیربنا؛ بقیه در فاز ۲)

- **الان:** `ROOM_PROVIDER` خالی است و «ورود به کلاس» همان لینکی را باز می‌کند که در صفحه رویداد وارد شده است. فرقش با قبل این است که لینک از مسیر `/account/registrations/<شماره>/join/` باز می‌شود و فقط به ثبت‌نام قطعی‌شده داده می‌شود.
- **در فاز ۲:** یک آداپتر برای سرویس واقعی (پیشنهاد: اسکای‌روم با وب‌سرویس) نوشته می‌شود و نامش در `ROOM_PROVIDER` قرار می‌گیرد. قبل از روشن کردن:
  ```bash
  docker exec -it hrweb-production-web-1 python manage.py check_rooms
  ```
- **اگر سرویس قطع شود:** کلاس با لینک واردشده در صفحه رویداد باز می‌شود. پس برای رویدادهای مهم، لینک دستی را هم پر نگه دارید.
