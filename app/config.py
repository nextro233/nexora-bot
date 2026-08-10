import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip("'\" \t\r\n")
BOT_USERNAME = os.getenv("BOT_USERNAME", "nexorasup_bot").strip("'\" \t\r\n@")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0").strip("'\" \t\r\n") or "0")

SULGX_URL = os.getenv("SULGX_URL", "https://web-production-267e1.up.railway.app").strip("'\" \t\r\n").rstrip("/")
SULGX_PASSWORD = os.getenv("SULGX_PASSWORD", "admin").strip("'\" \t\r\n")

STARZ_BOT_USERNAME = os.getenv("STARZ_BOT_USERNAME", "@StarzFaBot")
DB_PATH = os.getenv("DB_PATH", "/data/workspace/nexora-bot/nexora.db")

FREE_TEST_MB = int(os.getenv("FREE_TEST_MB", "50"))
BASE_PRICE_PER_GB = int(os.getenv("BASE_PRICE_PER_GB", "5000"))
VOLUME_ALERT_THRESHOLD_GB = float(os.getenv("VOLUME_ALERT_THRESHOLD_GB", "100.0"))

# Railway free-plan expiry tracking — set this in Railway Variables once deployed.
# Format: ISO datetime string, e.g. "2026-08-10T15:00:00+00:00"
# If not set, the scheduler falls back to the first order's created_at date.
RAILWAY_DEPLOY_START = os.getenv("RAILWAY_DEPLOY_START", "")

# Price packages with marketing discounts
# Basis: 1 Star ≈ 5,550 toman (100 Stars = $3 = 555,000 toman at 185k rate)
STAR_TO_TOMAN = 5550

def _plan(gb: int, discount_pct: int, label: str) -> dict:
    """Build a plan with consistent toman/stars pricing.
    price_toman = base price per GB * GB * (1 - discount)
    stars = ceil(price_toman / STAR_TO_TOMAN) — always covers the toman price,
    rounded once, consistent across plans.
    """
    import math
    per_gb = BASE_PRICE_PER_GB * (1 - discount_pct / 100)
    price_toman = int(per_gb * gb)
    stars = math.ceil(price_toman / STAR_TO_TOMAN)
    return {
        "gb": gb,
        "price_toman": price_toman,
        "stars": stars,
        "discount": discount_pct,
        "label": label,
    }

PLANS = {
    5: _plan(5, 0, "📦 5 گیگابایت (پایه)"),
    10: _plan(10, 5, "🔥 10 گیگابایت (5% تخفیف)"),
    20: _plan(20, 10, "⚡ 20 گیگابایت (10% تخفیف)"),
    30: _plan(30, 15, "🚀 30 گیگابایت (15% تخفیف)"),
    50: _plan(50, 20, "👑 50 گیگابایت (20% تخفیف)"),
}
