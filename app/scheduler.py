import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app import database

scheduler = AsyncIOScheduler()

async def _deactivate_unpaid(order_id: int, uuid: str):
    from app.services.sulgx import sulgx_client
    from bot import bot
    from app import config

    order = database.get_order(order_id)
    if not order:
        return
    if order["status"] in ("active", "payment_received"):
        return  # Already paid

    # Deactivate on panel
    try:
        await sulgx_client.set_link_status(uuid, active=False)
        database.deactivate_service(uuid)
    except Exception as e:
        print(f"Auto-deactivate error: {e}")
        return

    database.set_order_status(order_id, "cancelled")
    # Notify user
    try:
        await bot.send_message(
            order["telegram_id"],
            "⏰ **زمان پرداخت سفارش شما تمام شد.**\n\n"
            "پرداخت استارز در مهلت ۵ دقیقه‌ای تکمیل نشد. سرویس موقتاً غیرفعال شد.\n"
            "اگر همچنان مایل به خرید هستید، می‌توانید دوباره سفارش دهید.\n\n"
            "💡 *اگر پرداخت را انجام داده‌اید ولی سیستم ثبت نکرده، لطفاً با پشتیبانی در میان بگذارید — به سرعت بررسی می‌کنیم.*",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Notify user error: {e}")


def schedule_payment_timeout(order_id: int, uuid: str):
    from datetime import datetime, timedelta
    run_time = datetime.now() + timedelta(minutes=5)
    scheduler.add_job(
        _deactivate_unpaid,
        trigger="date",
        run_date=run_time,
        args=[order_id, uuid],
        id=f"payment_timeout_{order_id}",
        replace_existing=True,
        misfire_grace_time=120
    )


def start_scheduler():
    scheduler.start()