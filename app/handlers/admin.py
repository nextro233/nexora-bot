"""Admin handlers: deliver configs, 5-minute payment grace window, /reply, etc."""
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, types
from app import database, config
from app.services.sulgx import sulgx_client

router = Router()
logger = logging.getLogger(__name__)
ADMIN_ID = config.ADMIN_ID
PAYMENT_GRACE_MINUTES = 5

# Memory: admins awaiting link input (order_id)
_pending_deliveries: dict = {}


@router.message(F.text == "/admin", F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    from app.database import get_conn
    with get_conn() as conn:
        users_count = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        orders_count = conn.execute("SELECT COUNT(*) as c FROM orders").fetchone()["c"]
        revenue_toman = conn.execute(
            "SELECT COALESCE(SUM(price_toman),0) as s FROM orders WHERE status IN ('paid','active','payment_received')"
        ).fetchone()["s"]
        total_gb = conn.execute("SELECT COALESCE(SUM(volume_gb),0) as s FROM services").fetchone()["s"]
        pending_deliveries = conn.execute(
            "SELECT COUNT(*) as c FROM orders WHERE status='delivered' AND payment_charge_id IS NULL"
        ).fetchone()["c"]

    text = (
        f"👨‍💻 **پنل مدیریت NEXORA**\n\n"
        f"👥 کاربران: **{users_count}**\n"
        f"🧾 سفارش‌ها: **{orders_count}**\n"
        f"💵 درآمد (پرداخت‌شده): **{revenue_toman:,} تومان**\n"
        f"📦 کل گیگ فروخته‌شده: **{total_gb:.1f} GB**\n"
        f"⏳ منتظر پرداخت: **{pending_deliveries}**\n\n"
        f"⚙️ **دستورات ادمین:**\n"
        f"`/admin` — این پنل\n"
        f"`/order 5` — جزئیات سفارش\n"
        f"`/deliver 5 لینک` — تحویل کانفیگ (+ تایمر ۵ دقیقه)\n"
        f"`/delivered` — فهرست سفارشات منتظر پرداخت\n"
        f"`/reply آیدی متن` — پاسخ به مشتری\n"
        f"`/backup` — بکاپ دیتابیس (تلگرام + گیت‌هاب)\n"
        f"`/total_volume` — کل فروش\n"
        f"`/broadcast پیام` — ارسال پیام به همه"
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(F.text.startswith("/deliver"), F.from_user.id == ADMIN_ID)
async def deliver_config(message: types.Message):
    """Admin: /deliver <order_id> [link]
    - With link:  sends it to customer, starts 5-min payment grace timer.
    - Without link: just starts the timer (config already sent manually)."""
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer(
            "📦 **تحویل کانفیگ**\n\n"
            "فرمت:\n"
            "`/deliver 5` — فقط تایمر ۵ دقیقه (کانفیگ قبلاً ارسال شده)\n"
            "`/deliver 5 vless://...` — ارسال کانفیگ + تایمر\n\n"
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
        user_row = conn.execute("SELECT * FROM users WHERE telegram_id=?", (order["telegram_id"],)).fetchone() if order else None

    if not order:
        await message.answer(f"❌ سفارش #{order_id} یافت نشد.")
        return

    # Determine if a link was passed inline
    vless_link = None
    if len(parts) >= 3 and parts[2].strip():
        candidate = parts[2].strip()
        if candidate.startswith(("vless://", "vmess://", "trojan://", "ss://", "hysteria://")):
            vless_link = candidate

    # Send config if link provided
    if vless_link:
        await _send_config_to_user(message, order, vless_link)

    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET status='delivered', config_delivered_at=?, delivery_note=? WHERE id=?",
            (datetime.utcnow().isoformat(timespec="seconds"), f"nexora_{order_id}_{order['telegram_id']}", order_id)
        )
        conn.commit()

    # Build a customer-facing receipt link: https://t.me/BotUsername?start=bought_<order_id>
    from app.instances import bot
    try:
        bot_info = await bot.me()
        bot_username = bot_info.username
    except Exception:
        bot_username = "nexorasup_bot"  # fallback

    receipt_link = f"https://t.me/{bot_username}?start=bought_{order_id}"

    # Notify admin
    await message.answer(
        f"✅ سفارش #{order_id} — کانفیگ ارسال شد + تایمر ۵ دقیقه فعال شد!\n"
        f"⏳ اگر پرداخت نشود، منقضی می‌شود و به ادمین اطلاع داده می‌شود.\n\n"
        f"🔗 لینک رسید مشتری: {receipt_link}\n"
        f"📋 اسم پنل: `nexora_{order_id}_{order['telegram_id']}`",
        parse_mode="Markdown"
    )


async def _send_config_to_user(message: types.Message, order, vless_link: str):
    """Send VLESS config to the customer and tell them about the 5-min grace window."""
    from app.instances import bot
    grace_min = PAYMENT_GRACE_MINUTES
    await bot.send_message(
        order["telegram_id"],
        f"🚀 **کانفیگ شما آماده است!**\n\n"
        f"🔗 **لینک اتصال (VLESS):**\n`{vless_link}`\n\n"
        f"📦 حجم: {order['plan_gb']} گیگابایت\n\n"
        f"💡 برای اتصال از اپ **v2rayNG** (اندروید) یا **V2Box** (آیفون) استفاده کنید.\n\n"
        f"⏰ **تا {grace_min} دقیقه وقت دارید تا استارز خود را پرداخت کنید.**\n"
        f"بعد از پرداخت موفق، دکمه «✅ پرداخت {order['price_stars']} استارز» را بزنید تا سرویس فعال شود.\n\n"
        f"⚠️ اگر در {grace_min} دقیقه پرداخت نکنید، لینک غیرفعال می‌شود و ادمین به شما اطلاع می‌دهد.",
        parse_mode="Markdown"
    )


# ─── Two-step delivery (send /deliver first, then the link) ───
_pending_deliveries: dict = {}


@router.message(F.from_user.id == ADMIN_ID)
async def catch_delivery_link(message: types.Message):
    """If admin sends a link right after `/deliver <id>` (no link inline), send it to the user."""
    admin_id = message.from_user.id
    if admin_id not in _pending_deliveries:
        return

    order_id = _pending_deliveries.pop(admin_id)
    vless_link = message.text.strip() if message.text else ""

    if not vless_link.startswith(("vless://", "vmess://", "trojan://", "ss://", "hysteria://")):
        await message.answer("⚠️ این لینک معتبر به نظر نمی‌رسد. لینک شروع‌شونده با vless:// بفرست.")
        return

    from app.database import get_conn
    from app.scheduler import schedule_payment_grace
    with get_conn() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()

    if not order:
        await message.answer("❌ سفارش یافت نشد.")
        return

    await _send_config_to_user(message, order, vless_link)

    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET status='delivered', config_delivered_at=?, delivery_note=? WHERE id=?",
            (datetime.utcnow().isoformat(timespec="seconds"), f"nexora_{order_id}_{order['telegram_id']}", order_id)
        )
        conn.commit()

    # Start the 5-min payment grace timer
    from app.scheduler import schedule_payment_grace
    schedule_payment_grace(order_id)

    from app.instances import bot
    try:
        bot_info = await bot.get_me()
        bot_username = bot_info.username
    except Exception:
        bot_username = "nexorasup_bot"

    receipt_link = f"https://t.me/{bot_username}?start=bought_{order_id}"

    await message.answer(
        f"✅ کانفیگ برای سفارش #{order_id} ارسال شد + تایمر ۵ دقیقه فعال شد.\n\n"
        f"🔗 لینک رسید مشتری: {receipt_link}\n"
        f"📋 اسم پنل: `nexora_{order_id}_{order['telegram_id']}`",
        parse_mode="Markdown"
    )


@router.message(F.from_user.id == ADMIN_ID, F.text == "/cancel_delivery")
async def cancel_delivery(message: types.Message):
    _pending_deliveries.pop(message.from_user.id, None)
    await message.answer("انصراف از تحویل. سفارش دستی قابل مدیریت است.")


@router.message(F.text == "/delivered", F.from_user.id == ADMIN_ID)
async def list_delivered(message: types.Message):
    """Admin: /delivered — list orders pending payment after config delivery."""
    from app.database import get_conn
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, telegram_id, plan_gb, price_stars, config_delivered_at "
            "FROM orders WHERE status='delivered' ORDER BY id DESC LIMIT 20"
        ).fetchall()

    if not rows:
        await message.answer("📭 هیچ سفارش منتظر پرداختی نیست.")
        return

    lines = ["📋 **سفارشات منتظر پرداخت:**\n"]
    for row in rows:
        lines.append(
            f"#{row['id']} | `{row['telegram_id']}` | {row['plan_gb']}گیگ | ⭐{row['price_stars']} | "
            f"زمان تحویل: {row['config_delivered_at'] or '—'}"
        )
    await message.answer("\n".join(lines), parse_mode="Markdown")


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
        "delivered": "📦 تحویل شده (در انتظار پرداخت نهایی)",
        "active": "✅ فعال",
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
        f"💡 برای ساخت کانفیگ در پنل، اسم را `nexora_{order['id']}_{order['telegram_id']}` بگذارید.\n\n"
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
            "مثال:\n`/reply 5860341769 سلام، مشکل شما بررسی شد ✅`",
            parse_mode="Markdown"
        )
        return

    user_id_str = parts[1].strip()
    if not user_id_str.isdigit():
        await message.answer("❌ آیدی کاربر باید عدد باشد.")
        return

    user_id = int(user_id_str)
    reply_text = parts[2].strip()

    from app.instances import bot
    try:
        await bot.send_message(
            user_id,
            f"💬 **پاسخ پشتیبانی NEXORA**\n\n{reply_text}\n\n"
            f"📩 اگر سوال دیگری دارید، از «📩 گزارش مشکل / پشتیبانی» پیام بدهید.",
            parse_mode="Markdown"
        )
        await message.answer(f"✅ پاسخ به کاربر `{user_id}` ارسال شد.")
    except Exception as e:
        logger.error(f"Reply failed: {e}")
        await message.answer(
            f"❌ ارسال پاسخ ممکن نشد. احتمالاً کاربر ربات را بلاک کرده یا شروع نکرده است.\nخطا: {type(e).__name__}"
        )


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
        f"⚡*به محض رسیدن به {threshold:g} گیگ، اطلاع‌رسانی خودکار انجام می‌شود.*"
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
    from app.instances import bot
    for u in users:
        try:
            await bot.send_message(u["telegram_id"], text)
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