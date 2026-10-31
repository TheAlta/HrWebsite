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
mkdir -p /srv/hrweb/{production,staging}/{media,postgres,backups} /srv/hrweb/caddy/{data,config}
chown -R 1000:1000 /srv/hrweb/production/media /srv/hrweb/staging/media
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

1. **Settings ← Sites:** نام میزبان را `arezoo-zahmatbaran.ir` و پورت را `443` بگذارید. آدرس canonical از این‌جا ساخته می‌شود.
2. **Settings ← تنظیمات سایت:** تماس، واتساپ، منو، ایمیل و موبایل اعلان‌ها.
3. **رزرو جلسه:** انواع جلسه، ساعات کاری، مرخصی‌ها.

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

این‌ها در بخش ۱۱ سند الزامی‌اند و هنوز انجام نشده‌اند (REPORT #040):

- [ ] احراز دومرحله‌ای برای پنل مدیریت
- [ ] محدودیت تلاش ورود به پنل
- [ ] هدرهای CSP
- [ ] تغییر مسیر پیش‌فرض پنل (`WAGTAIL_ADMIN_PATH` و `DJANGO_ADMIN_PATH`)
- [ ] تست پرداخت واقعی با زرین‌پال و زیبال
