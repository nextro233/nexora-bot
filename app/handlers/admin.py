from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from app import database, config
from app.services.sulgx import sulgx_client
import logging

router = Router()
logger = logging.getLogger(__name__)

ADMIN_ID = config.ADMIN_ID

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

@router.message(F.text == "/admin", F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    users_count = 0
    orders_count = 0
    revenue_toman = 0
    total_gb = 0
    
    from app.database import get_conn
    with get_conn() as conn:
        users_count = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        orders_count = conn.execute("SELECT COUNT(*) as c FROM orders").fetchone()["c"]
        revenue_toman = conn.execute("SELECT COALESCE(SUM(price_toman),0) as s FROM orders WHERE status='active' OR status='payment_received'").fetchone()["s"]
        total_gb = conn.execute("SELECT COALESCE(SUM(volume_gb),0) as s FROM services").fetchone()["s"]
    
    text = (
        f"👨‍💻 **پنل مدیریت NEXORA**\n\n"
        f"👥 تعداد کاربران: **{users_count}**\n"
        f"🧾 تعداد سفارش‌ها: **{orders_count}**\n"
        f"💵 درآمد (پرداخت‌شده): **{revenue_toman:,} تومان**\n"
        f"📦 کل گیگ فروخته‌شده: **{total_gb:.1f} GB**\n\n"
        f"⚙️ **دستورات ادمین:**\n"
        f"`/admin` — این پنل\n"
        f"`/total_volume` — کل فروش\n"
        f"`/broadcast پیام` — ارسال پیام به همه"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(F.text == "/total_volume", F.from_user.id == ADMIN_ID)
async def total_volume(message: types.Message):
    total_gb = database.total_sold_gb_all()
    threshold = config.VOLUME_ALERT_THRESHOLD_GB
    remaining = max(threshold - total_gb, 0)
    
    text = (
        f"📦 **کل فروش حجمی**\n\n"
        f"مجموع گیگ فروخته‌شده: **{total_gb:.1f} GB**\n"
        f"هدف هشدار: {threshold:g} GB\n"
        f"تا رسیدن به هدف: {remaining:.1f} GB\n\n"
        f"⚡ *به محض رسیدن به {threshold:g} گیگ، اطلاع‌رسانی خودکار انجام می‌شود.*"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(F.text.startswith("/broadcast "), F.from_user.id == ADMIN_ID)
async def broadcast(message: types.Message):
    text = message.text.replace("/broadcast ", "", 1).strip()
    if not text:
        await message.answer("فرمت: `/broadcast متن پیام`", parse_mode="Markdown")
        return
    
    from app.database import get_conn
    with get_conn() as conn:
        users = conn.execute("SELECT telegram_id FROM users").fetchall()
    
    sent = 0
    for u in users:
        try:
            await message.bot.send_message(u["telegram_id"], text)
            sent += 1
        except Exception:
            continue
    
    await message.answer(f"✅ پیام همگانی به {sent} کاربر ارسال شد (از {len(users)} کل).")