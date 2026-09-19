# بحساب — Telegram Mini App

«بحساب» یک مینی‌اپ فارسی و RTL برای حساب‌وکتاب **دونفره** است. بخش گروه وجود ندارد؛ هر رابطه مالی فقط بین دو کاربر مستقل نگهداری می‌شود.

## قابلیت‌ها

- ورود بدون شماره تلفن و رمز عبور با Telegram Mini Apps `initData`
- اعتبارسنجی `initData` در بک‌اند با HMAC-SHA-256
- درخواست دوستی و تأیید/رد توسط طرف مقابل
- زنگوله درخواست‌های دوستی داخل اپ
- صفحه مستقل برای هر دوست و نمایش ریز تراکنش‌ها
- ثبت بدهی و ثبت تسویه در هر دو جهت
- ویرایش و حذف تراکنش + محاسبه مجدد مانده
- نوتیفیکیشن تلگرام برای درخواست دوستی، تأیید، ثبت، ویرایش و حذف تراکنش
- یک دکمه شیشه‌ای بزرگ «🚀 ورود به بحساب» زیر پیام‌های ربات
- بخش «شخصی» برای ثبت/ویرایش/حذف هزینه‌های فردی
- پروفایل کاربر
- PostgreSQL روی Render و SQLite در اجرای محلی
- فرانت‌اند HTML/CSS/JavaScript بدون Node.js build
- تم سرمه‌ای تیره + فیروزه‌ای

## ساختار پروژه

```text
behesab-miniapp/
├─ app/
│  ├─ main.py
│  ├─ db.py
│  ├─ models.py
│  ├─ telegram_auth.py
│  ├─ telegram_bot.py
│  └─ static/
│     ├─ index.html
│     ├─ styles.css
│     └─ app.js
├─ requirements.txt
├─ render.yaml
├─ .env.example
└─ README.md
```

## اجرای محلی

Python 3.12 پیشنهاد می‌شود.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

یک فایل `.env` بر اساس `.env.example` بسازید. برای تست خارج از Telegram:

```env
DATABASE_URL=sqlite:///./behesab.db
DEV_MODE=true
```

سپس متغیرها را در محیط سیستم بارگذاری کنید و اجرا کنید:

```bash
uvicorn app.main:app --reload
```

برای تست محلی ساده می‌توانید مرورگر را با این آدرس باز کنید:

```text
http://127.0.0.1:8000/?dev=1001
```

برای ساخت کاربر دوم، یک‌بار با `?dev=1002` باز کنید. سپس کاربر 1001 می‌تواند `1002` را به عنوان دوست اضافه کند.

> حالت `DEV_MODE` فقط برای توسعه محلی است و در `render.yaml` خاموش است.

## ساخت ربات Telegram

1. در BotFather یک Bot بسازید و `BOT_TOKEN` را بگیرید.
2. پروژه را Deploy کنید تا آدرس HTTPS داشته باشید.
3. `BOT_TOKEN` و `PUBLIC_URL` را در Environment Variables سرویس Render تنظیم کنید.
4. برنامه هنگام Startup به‌صورت خودکار Webhook را روی مسیر `/api/telegram/webhook` تنظیم می‌کند.
5. در BotFather، دامنه Mini App را در صورت نیاز برای Bot/Web App تنظیم کنید.
6. در ربات `/start` بزنید؛ پیام خوش‌آمد با دکمه «🚀 ورود به بحساب» نمایش داده می‌شود.

## Deploy روی GitHub + Render

1. کل پوشه پروژه را در یک Repository جدید GitHub آپلود کنید.
2. در Render وارد **Blueprints** شوید.
3. Repository را انتخاب کنید.
4. Render فایل `render.yaml` را می‌خواند و Web Service + PostgreSQL را می‌سازد.
5. هنگام ایجاد Blueprint مقدار `BOT_TOKEN` و `PUBLIC_URL` را وارد کنید. اگر URL سرویس هنوز مشخص نیست، پس از ساخته‌شدن سرویس، `PUBLIC_URL` را مانند زیر در Environment قرار دهید و Deploy مجدد کنید:

```text
https://YOUR-SERVICE.onrender.com
```

6. `DEV_MODE` در Render باید `false` باقی بماند.

## نکته درباره اضافه‌کردن دوست

برای اینکه کاربری با `@username` یا Telegram ID پیدا شود، آن شخص باید حداقل یک‌بار ربات یا Mini App «بحساب» را باز کرده باشد تا اطلاعات Telegram او در دیتابیس ثبت شود.

## منطق مانده

- `debt`: یک تعهد مالی ایجاد می‌کند.
- `settlement`: پرداخت انجام‌شده را از مانده تعهد کم می‌کند.
- در UI، مانده مثبت یعنی شما طلبکارید و مانده منفی یعنی بدهکارید.

## امنیت

- فرانت‌اند به `initDataUnsafe` برای احراز هویت اعتماد نمی‌کند.
- رشته خام `Telegram.WebApp.initData` به سرور ارسال و با Bot Token اعتبارسنجی می‌شود.
- Webhook ربات با `secret_token` محافظت می‌شود.
- Secretها در Git ذخیره نمی‌شوند.

## APIهای اصلی

- `GET /api/me`
- `GET /api/friends`
- `GET /api/friends/requests`
- `POST /api/friends/requests`
- `POST /api/friends/requests/{id}/accept`
- `POST /api/friends/requests/{id}/reject`
- `GET /api/friends/{friend_id}/transactions`
- `POST /api/friends/{friend_id}/transactions`
- `PUT /api/transactions/{id}`
- `DELETE /api/transactions/{id}`
- `GET/POST /api/personal`
- `PUT/DELETE /api/personal/{id}`
- `POST /api/telegram/webhook`

## نکته تولیدی

برای نسخه بزرگ‌تر بهتر است Alembic برای migration، logging ساختاریافته، rate limiting و تست‌های integration اضافه شوند.
