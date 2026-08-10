import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "nexorasup_bot")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

SULGX_URL = os.getenv("SULGX_URL", "https://web-production-267e1.up.railway.app").rstrip("/")
SULGX_PASSWORD = os.getenv("SULGX_PASSWORD", "admin")

STARZ_BOT_USERNAME = os.getenv("STARZ_BOT_USERNAME", "@StarzFaBot")
DB_PATH = os.getenv("DB_PATH", "/data/workspace/nexora-bot/nexora.db")

FREE_TEST_MB = int(os.getenv("FREE_TEST_MB", "50"))
BASE_PRICE_PER_GB = int(os.getenv("BASE_PRICE_PER_GB", "5000"))
VOLUME_ALERT_THRESHOLD_GB = float(os.getenv("VOLUME_ALERT_THRESHOLD_GB", "100.0"))

# Price packages with marketing discounts
# Basis: 1 Star ≈ 5,550 toman (100 Stars = $3 = 555,000 toman at 185k rate)
STAR_TO_TOMAN = 5550
PLANS = {
    5: {"gb": 5, "price_toman": 25000, "stars": 5, "discount": 0, "label": "📦 5 گیگابایت (پایه)"},
    10: {"gb": 10, "price_toman": 47500, "stars": 9, "discount": 5, "label": "🔥 10 گیگابایت (5% تخفیف)"},
    20: {"gb": 20, "price_toman": 90000, "stars": 17, "discount": 10, "label": "⚡ 20 گیگابایت (10% تخفیف)"},
    30: {"gb": 30, "price_toman": 127500, "stars": 23, "discount": 15, "label": "🚀 30 گیگابایت (15% تخفیف)"},
    50: {"gb": 50, "price_toman": 200000, "stars": 36, "discount": 20, "label": "👑 50 گیگابایت (20% تخفیف)"},
}
