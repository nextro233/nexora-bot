# NEXORA Telegram Sales Bot

ربات فروش کانفیگ VLESS حجمی با پرداخت تلگرام استارز — NEXORA

## امکانات
- 🧪 تست رایگان ۵۰ مگابایت (هر کاربر یک بار)
- 🛒 فروش بسته‌های ۵ تا ۵۰ گیگابایت با تخفیف پلکانی
- 🚀 تحویل کانفیگ پیش از پرداخت (مهلت ۵ دقیقه)
- ⭐ پرداخت با تلگرام استارز (Stars)
- 📊 مشاهده حجم مصرفی آنلاین
- 📩 سیستم تیکت پشتیبانی
- 🔔 هشدار ادمین هنگام رسیدن فروش به ۱۰۰ گیگ

## راه‌اندازی (محلی)
```bash
pip install -r requirements.txt
cp .env.example .env
# مقادیر واقعی را در .env وارد کنید
python bot.py
```

## راه‌اندازی روی Railway
1. این ریپازیتوری را به گیت‌هاب پوش کنید
2. در Railway از گزینه Deploy from GitHub استفاده کنید
3. در تب Variables متغیرهای .env را وارد کنید
4. دیپلوی کنید — آماده است!

## متغیرهای محیطی (Variables)
| متغیر | توضیح |
|-------|-------|
| `BOT_TOKEN` | توکن ربات تلگرام |
| `ADMIN_ID` | آیدی عددی ادمین (دریافت از @userinfobot) |
| `SULGX_URL` | آدرس پنل SulgX |
| `SULGX_PASSWORD` | رمز پنل SulgX |
| `BOT_USERNAME` | یوزرنیم بات (بدون @) |
| `STARZ_BOT_USERNAME` | ربات فروش استارز |
| `FREE_TEST_MB` | حجم تست رایگان (مگابایت) |
| `BASE_PRICE_PER_GB` | قیمت پایه هر گیگ (تومان) |
| `VOLUME_ALERT_THRESHOLD_GB` | آستانه هشدار فروش (گیگ) |

## ساختار پروژه
```
app/
├── config.py          # تنظیمات و پلن‌ها
├── database.py        # دیتابیس SQLite
├── scheduler.py       # زمان‌بندی غیرفعال‌سازی
├── handlers/
│   ├── start.py       # /start و راهنما
│   ├── test.py        # تست رایگان
│   ├── shop.py        # فروشگاه
│   ├── payment.py     # پرداخت استارز
│   ├── service.py     # وضعیت سرویس
│   ├── support.py     # پشتیبانی
│   └── admin.py       # پنل ادمین
├── services/
│   └── sulgx.py       # اتصال به پنل SulgX
└── keyboards/
    └── main.py        # کیبوردها
```

## پنل ادمین
- `/admin` — آمار کامل
- `/broadcast پیام` — ارسال همگانی
- `/total_volume` — مجموع فروش