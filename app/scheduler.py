"""Scheduler: daily DB backup to GitHub/admin + Railway free-plan expiry warning."""
import asyncio
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import database, config

scheduler = AsyncIOScheduler()

# When Railway free trial started (approx — first user created). Filled at startup.
_DEPLOY_START = None

# Backups are sent once per day (and on demand via /backup)
_BACKUP_KEY = "last_backup_date"


async def _daily_backup():
    """Send DB backup to admin chat + GitHub every day."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    last = database.get_setting(_BACKUP_KEY)
    if last == today:
        return  # already backed up today
    try:
        from app.backup import send_backup_to_admin
        msg = await send_backup_to_admin()
        print(f"[backup] {msg}")
        database.set_setting(_BACKUP_KEY, today)
    except Exception as e:
        print(f"[backup] failed: {e}")


async def _railway_plan_warning():
    """Warn admin ~5 days before Railway free plan's 30-day limit (day 25+)."""
    if _DEPLOY_START is None:
        return
    days_elapsed = (datetime.utcnow() - _DEPLOY_START).days
    if days_elapsed >= 25:
        try:
            from app.instances import bot
            await bot.send_message(
                config.ADMIN_ID,
                f"⚠️ **هشدار اعتبار Railway**\n\n"
                f"⏳ {days_elapsed} روز از شروع فعالیت گذشته است.\n"
                f"اعتبار **رایگان ۳۰ روزه** Railway ممکن است به‌زودی پایان یابد.\n\n"
                f"📦 **برای جلوگیری از قطعی:**\n"
                f"1️⃣ بکاپ بگیرید: `/backup`\n"
                f"2️⃣ یک پروژه جدید Railway بسازید\n"
                f"3️⃣ دیتابیس بکاپ را منتقل کنید\n\n"
                f"🔒 همه اطلاعات مشتریان در بکاپ حفظ می‌شود.",
                parse_mode="Markdown",
            )
        except Exception as e:
            print(f"[railway warning] failed: {e}")


def start_scheduler():
    global _DEPLOY_START
    try:
        from app.backup import get_deploy_start_date
        _DEPLOY_START = get_deploy_start_date()
    except Exception:
        _DEPLOY_START = datetime.utcnow()

    # Daily backup at 03:00 UTC
    scheduler.add_job(
        _daily_backup,
        trigger="cron",
        hour=3,
        minute=0,
        id="daily_backup",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # Railway plan warning daily at 09:00 UTC
    scheduler.add_job(
        _railway_plan_warning,
        trigger="cron",
        hour=9,
        minute=0,
        id="railway_plan_warning",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()