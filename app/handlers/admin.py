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

@router.message(F.text.startswith("/deliver"), F.from_user.id == ADMIN_ID)
async def deliver_config(message: types.Message):
    """Admin command: /deliver <order_id> [link] — one-step or two-step delivery"""
    parts = message.text.split(maxsplit=2)
    # parts[0]=/deliver, parts[1]=order id, parts[2]=optional link
    
    if len(parts) < 2:
        await message.answer(
            "📦 **تحویل کانفیگ**\n\n"
            "دو روش:\n"
            "1️⃣ دو مرحله‌ای: `/deliver 2` بعد لینک رو بفرست\n"
            "2️⃣ یکجا: `/deliver 2 vless://...`\n\n"
            "هر دوتاش کار می‌کنه 👌",
            parse_mode="Markdown"
        )
        return
    
    order_id_str = parts[1].strip()
    if not order_id_str.isdigit():
        await message.answer("❌ شناسه سفارش باید عدد باشه. مثال: `/deliver 2`", parse_mode="Markdown")
        return
    
    order_id = int(order_id_str)
    from app.database import get_conn
    with get_conn() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    
    if not order:
        await message.answer(f"❌ سفارش #{order_id} یافت نشد.")
        return
    
    # If link was also provided, deliver immediately (one-step)
    if len(parts) >= 3:
        vless_link = parts[2].strip()
        if not vless_link.startswith(("vless://", "vmess://", "trojan://", "ss://", "hysteria://")):
            # maybe it's the whole rest of the line minus command
            rest = message.text.split(None, 1)[1].strip()  # "2 <link>"
            vless_link = rest.split(None, 1)[1].strip() if " " in rest else ""
            if not vless_link.startswith(("vless://", "vmess://", "trojan://", "ss://", "hysteria://")):
                await message.answer("⚠️ لینک معتبر نیست. لینکی که با vless:// شروع می‌شه بفرست.")
                return
        await _send_config_to_user(message, order, vless_link)
        await message.answer(f"✅ کانفیگ سفارش #{order_id} ارسال شد!")
        return
    
    # Two-step: store and ask for link
    await message.answer(
        f"🛠 **کانفیگ برای سفارش #{order_id}**\n"
        f"کاربر: `{order['telegram_id']}` | {order['plan_gb']} گیگابایت\n\n"
        f"حالا **لینک VLESS** رو بفرست تا بره برای کاربر.\n"
        f"(یا /cancel_delivery برای انصراف)",
        parse_mode="Markdown"
    )
    _pending_deliveries[message.from_user.id] = order_id

_pending_deliveries: dict = {}


async def _send_config_to_user(message: types.Message, order, vless_link: str):
    """Send the VLESS config to the customer and mark order as delivered."""
    from app.instances import bot
    user_id = order["telegram_id"]
    await bot.send_message(
        user_id,
        f"🚀 **کانفیگ شما آماده است!**\n\n"
        f"🔗 **لینک اتصال (VLESS):**\n`{vless_link}`\n\n"
        f"📦 حجم: {order['plan_gb']} گیگابایت\n\n"
        f"💡 *برای اتصال از اپ v2rayNG (اندروید) یا V2Box (آیفون) استفاده کنید.*\n\n"
        f"✅ اگر پرداخت رو انجام دادید، دکمه «پرداخت انجام شد» رو بزنید.",
        parse_mode="Markdown"
    )
    # Mark order as delivered
    from app.database import get_conn
    with get_conn() as conn:
        conn.execute("UPDATE orders SET status='delivered' WHERE id=?", (order["id"],))
        conn.commit()


@router.message(F.from_user.id == ADMIN_ID)
async def catch_delivery_link(message: types.Message):
    """If admin sends a link right after /deliver, send it to the user"""
    admin_id = message.from_user.id
    if admin_id not in _pending_deliveries:
        return
    
    order_id = _pending_deliveries.pop(admin_id)
    vless_link = message.text.strip() if message.text else ""
    
    if not vless_link.startswith(("vless://", "vmess://", "trojan://", "ss://", "hysteria://")):
        await message.answer("⚠️ این لینک معتبر به نظر نمی‌رسد. لینک شروع‌شونده با vless:// بفرستید.")
        return
    
    from app.database import get_conn
    with get_conn() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    
    if not order:
        await message.answer("❌ سفارش یافت نشد.")
        return
    
    user_id = order["telegram_id"]
    from app.instances import bot
    await bot.send_message(
        user_id,
        f"🚀 **کانفیگ شما آماده است!**\n\n"
        f"🔗 **لینک اتصال (VLESS):**\n`{vless_link}`\n\n"
        f"📦 حجم: {order['plan_gb']} گیگابایت\n\n"
        f"💡 *برای اتصال از اپ v2rayNG (اندروید) یا V2Box (آیفون) استفاده کنید.*\n\n"
        f"✅ اگر پرداخت رو انجام دادید، دکمه «پرداخت انجام شد» رو بزنید.",
        parse_mode="Markdown"
    )
    # Mark order as delivered
    from app.database import get_conn
    with get_conn() as conn:
        conn.execute("UPDATE orders SET status='delivered' WHERE id=?", (order_id,))
        conn.commit()
    await message.answer(f"✅ کانفیگ برای سفارش #{order_id} ارسال شد!")


@router.message(F.from_user.id == ADMIN_ID, F.text == "/cancel_delivery")
async def cancel_delivery(message: types.Message):
    _pending_deliveries.pop(message.from_user.id, None)
    await message.answer("انصراف از تحویل. سفارش دستی قابل مدیریت است.")


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