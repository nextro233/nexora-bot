import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, types
from app import database, config
from app.services.sulgx import sulgx_client

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
        revenue_toman = conn.execute("SELECT COALESCE(SUM(price_toman),0) as s FROM orders WHERE status='paid' OR status='active' OR status='payment_received'").fetchone()["s"]
        total_gb = conn.execute("SELECT COALESCE(SUM(volume_gb),0) as s FROM services").fetchone()["s"]
    
    text = (
        f"👨‍💻 **پنل مدیریت NEXORA**\n\n"
        f"👥 تعداد کاربران: **{users_count}**\n"
        f"🧾 تعداد سفارش‌ها: **{orders_count}**\n"
        f"💵 درآمد (پرداخت‌شده): **{revenue_toman:,} تومان**\n"
        f"📦 کل گیگ فروخته‌شده: **{total_gb:.1f} GB**\n\n"
        f"⚙️ **دستورات ادمین:**\n"
        f"`/admin` — این پنل\n"
        f"`/order 5` — جزئیات سفارش (برای تطبیق کانفیگ با مشتری)\n"
        f"`/deliver 5 لینک` — تحویل کانفیگ\n"
        f"`/reply آیدی متن` — پاسخ به مشتری (بدون نیاز به یوزرنیم)\n"
        f"`/backup` — بکاپ دیتابیس (تلگرام + گیت‌هاب)\n"
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
        f"✅ اگر پرداخت رو انجام دادید، کانفیگ آماده استفاده است.",
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
        f"✅ اگر پرداخت رو انجام دادید، کانفیگ آماده استفاده است.",
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


@router.message(F.text == "/backup", F.from_user.id == ADMIN_ID)
async def backup_now(message: types.Message):
    """Admin: /backup — send DB backup to admin chat + GitHub now."""
    await message.answer("📦 در حال گرفتن بکاپ... لطفاً چند لحظه صبر کنید.")
    try:
        from app.backup import send_backup_to_admin
        msg = await send_backup_to_admin()
        await message.answer(f"✅ {msg}")
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        await message.answer(f"❌ بکاپ ناموفق بود: {type(e).__name__}")


@router.message(F.text.startswith("/order "), F.from_user.id == ADMIN_ID)
async def order_details(message: types.Message):
    """Admin: /order <id> — show order details including customer identity for config matching."""
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer("فرمت: `/order 5`", parse_mode="Markdown")
        return

    order_id = int(parts[1].strip())
    from app.database import get_conn
    with get_conn() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        user = conn.execute("SELECT * FROM users WHERE telegram_id=?", (order["telegram_id"],)).fetchone() if order else None

    if not order:
        await message.answer(f"❌ سفارش #{order_id} یافت نشد.")
        return

    username = f"@{user['username']}" if user and user["username"] else "—"
    first = user["first_name"] if user else "—"
    status_map = {
        "pending": "🟡 در انتظار پرداخت",
        "paid": "🟢 پرداخت تأیید شده",
        "active": "✅ فعال",
        "delivered": "📦 تحویل شده",
        "cancelled": "❌ لغو شده",
    }

    text = (
        f"🧾 **جزئیات سفارش #{order_id}**\n\n"
        f"📦 حجم: {order['plan_gb']} گیگابایت\n"
        f"⭐ قیمت: {order['price_stars']} استارز\n"
        f"💵 معادل: {order['price_toman']:,} تومان\n"
        f"📌 وضعیت: {status_map.get(order['status'], order['status'])}\n\n"
        f"👤 مشتری: {first} ({username})\n"
        f"🆔 آیدی: `{order['telegram_id']}`\n\n"
        f"💡 *برای ساخت کانفیگ در پنل، اسم را `nexora_{order['id']}_{order['telegram_id']}` بگذارید تا همیشه مشخص باشد مال کیست.*\n\n"
        f"⚙️ تحویل: `/deliver {order_id} لینک-vless`"
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(F.text.startswith("/reply "), F.from_user.id == ADMIN_ID)
async def reply_to_user(message: types.Message):
    """Admin: /reply <user_id> <text> — reply to a customer directly, no username needed."""
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            "📩 **پاسخ به مشتری**\n\n"
            "فرمت: `/reply {آیدی کاربر} {متن پاسخ}`\n\n"
            "مثال:\n`/reply 5860341769 سلام، مشکل شما بررسی شد و حل شد ✅`",
            parse_mode="Markdown"
        )
        return
    
    user_id_str = parts[1].strip()
    if not user_id_str.isdigit():
        await message.answer("❌ آیدی کاربر باید عدد باشد (همون عددی که در تیکت اومده).")
        return
    
    user_id = int(user_id_str)
    reply_text = parts[2].strip()
    
    from app.instances import bot
    try:
        await bot.send_message(
            user_id,
            f"💬 **پاسخ پشتیبانی NEXORA**\n\n{reply_text}\n\n"
            f"📩 اگر سوال دیگری دارید، از «📩 گزارش مشکل / پشتیبانی» پیام دهید.",
            parse_mode="Markdown"
        )
        await message.answer(f"✅ پاسخ به کاربر `{user_id}` ارسال شد.")
    except Exception as e:
        logger.error(f"Reply failed: {e}")
        await message.answer(
            f"❌ ارسال پاسخ ممکن نشد. احتمالاً کاربر ربات را بلاک کرده یا شروع نکرده است.\n"
            f"خطا: {type(e).__name__}"
        )