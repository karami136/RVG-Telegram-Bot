# RVG Telegram Sales Bot

این پروژه یک ربات فروش تلگرام برای RVG است:
- پرداخت کارت‌به‌کارت
- ارسال رسید
- تأیید دستی ادمین
- ساخت خودکار کانفیگ در RVG
- ارسال لینک VLESS + QR
- PostgreSQL روی Railway
- پنل مدیریت داخل تلگرام

## 1) ساخت سرویس Railway

یک Project بساز و یک Service جدید از همین Repository اضافه کن.
Start Command:
`python bot.py`

برای دیتابیس، از Railway یک PostgreSQL اضافه کن و متغیر DATABASE_URL آن را به سرویس Bot وصل کن.

## 2) ساخت Node Key در RVG

در پنل RVG:
- وارد مدیریت Nodes/Node Keys شو.
- یک کلید جدید بساز.
- `can_manage = ON`
- برای این Bot بهتر است دسترسی‌های share را فقط به `links` و `usage` محدود کنی.
- کلید را فقط در Railway Secret به نام `RVG_NODE_KEY` قرار بده.

این پروژه از API رسمی Node Linking خود RVG استفاده می‌کند و برای ساخت کانفیگ به `/api/node/links` درخواست می‌زند.

## 3) Environment Variables

در Railway این‌ها را اضافه کن:

BOT_TOKEN=توکن جدید BotFather
OWNER_ID=80145544
RVG_BASE_URL=https://دامنه-عمومی-RVG
RVG_NODE_KEY=کلید-Node
CARD_NUMBER=شماره-کارت
CARD_HOLDER=کرمی
DATABASE_URL=postgresql+asyncpg://...
BOT_NAME=RVG Store
SUPPORT_USERNAME=repair_phone

توکن و کلید Node را داخل GitHub نگذار.

## 4) پلن‌های اولیه

در اولین اجرا اگر دیتابیس خالی باشد این سه پلن ساخته می‌شوند:
- 30GB / 30 روز
- 50GB / 30 روز
- 100GB / 30 روز

قیمت اولیه صفر است تا از پنل ادمین قیمت بدهی.

## 5) روند فروش

مشتری:
`خرید → انتخاب پلن → نمایش کارت → ارسال رسید`

ادمین:
`پنل مدیریت → سفارش‌های در انتظار → سفارش → تأیید پرداخت`

بعد از تأیید:
`RVG → ساخت کانفیگ → لینک + Subscription + QR → ارسال به مشتری`

## 6) تست

اول قیمت پلن‌ها را در:
`/admin → مدیریت پلن‌ها`
تنظیم کن.

سپس با یک اکانت دیگر:
`/start → خرید کانفیگ`

یک سفارش آزمایشی بساز، رسید را ارسال کن و از اکانت Owner روی «تأیید پرداخت» بزن.

اگر RVG Node Key درست باشد، ربات باید کانفیگ را بسازد و لینک و QR را ارسال کند.
