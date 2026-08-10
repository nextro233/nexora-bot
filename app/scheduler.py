"""Scheduler: payment-grace timers + daily backups + Railway plan-expiry warning."""
import asyncio
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import database, config

scheduler = AsyncIOScheduler()

PAYMENT_GRACE_MINUTES = 5
_BACKUP_KEY = "last_backup_date"


async def _payment_grace_exceeded(order_id: int):
    """Called when the 5-minute payment window expires.
    Notifies admin + customer; deactivates the panel config."""
    order = database.get_order(order_id)
    if not order:
        return

    # If paid in the meantime, nothing to do
    if order["status"] in ("paid", "active", "cancelled", "failed"):
        return

    from app.instances import bot
    from app.services.sulgx import sulgx_client

    # Deactivate the config on the panel (if a service exists)
    try:
        svc = database.get_service_for_user(order["telegram_id"])
        if svc:
            await sulgx_client.set_link_status(svc["uuid"], active=False)
            database.deactivate_service(svc["uuid"])
    except Exception as e:
        print(f"[grace] panel deactivation failed: {e}")

    # Mark order as expired (not cancellable, admin can retry / refund)
    database.set_order_status(order_id, "cancelled")

    # Notify admin
    try:
        await bot.send_message(
            config.ADMIN_ID,
            f"⏰ **سفارش #{order_id} منقضی شد — پرداخت نشد.**\n\n"
            f"🔗 کانفیگ غیرفعال شد.\n"
            f"اگر مشتری متقاضی بازگشت استارز باشد، از `/refund {order_id}` استفاده کنید.\n"
            f"برای بررسی: `/order {order_id}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[grace] admin notify failed: {e}")

    # Notify customer
    try:
        await bot.send_message(
            order["telegram_id"],
            f"⏰ **زمان پرداخت تموم شد.**\n\n"
            f"سفارش #{order_id} ({order['plan_gb']} گیگابایت)\n"
            f"لینک شما غیرفعال شد.\n\n"
            f"💡 اگر همچنان مایل به خرید هستید، می‌توانید دوباره از فروشگاه خرید کنید.\n"
            f"اگر مشکلی بود، «📩 گزارش مشکل / پشتیبانی» بزنید.",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[grace] customer notify failed: {e}")


def schedule_payment_grace(order_id: int):
    """Schedule the 5-minute payment-grace timer for an order."""
    run_time = datetime.now() + timedelta(minutes=PAYMENT_GRACE_MINUTES)
    try:
        scheduler.add_job(
            _payment_grace_exceeded,
            trigger="date",
            run_date=run_time,
            args=[order_id],
            id=f"grace_{order_id}",
            replace_existing=True,
            misfire_grace_time=300,
        )
        print(f"[scheduler] grace timer scheduled for order #{order_id} at {run_time.isoformat()}")
    except Exception as e:
        print(f"[scheduler] failed to schedule grace timer: {e}")


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
    if config.RAILWAY_DEPLOY_START:
        from dateutil.parser import isoparse
        from datetime import datetime, timezone
        deploy_start = isoparse(config.RAILWAY_DEPLOY_START) if isinstance(config.RAILWAY_DEPLOY_START, str) else config.RAILWAY_DEPLOY_START
        days_elapsed = (datetime.now(timezone.utc) - deploy_start).days
        if days_elapsed >= 25:
            try:
                from app.instances import bot
                await bot.send_message(
                    config.ADMIN_ID,
                    f"⚠️ **هشدار اعتبار Railway**\n\n"
                    f"⏳ {days_elapsed} روز از شروع فعالیت گذشته است.\n"
                    f"اعتبار **رایگان ۳۰ روزه** ممکن است به‌زودی تموم بشود.\n\n"
                    f"📦 **برای جلوگیری از قطعی:**\n"
                    f"1️⃣ بکاپ بگیرید: `/backup`\n"
                    f"2️⃣ یک پروژه جدید Railway بسازید\n"
                    f"3️⃣ دیتابیس بکاپ را منتقل کنید\n\n"
                    f"🔒 همه اطلاعات مشتریان در بکاپ حفظ می‌شود.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"[railway warning] failed: {e}")


def start_scheduler():
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