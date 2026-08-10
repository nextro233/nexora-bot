from aiogram import Router, F, types
from app import database, config
from app.keyboards.main import service_options_keyboard
from app.services.sulgx import sulgx_client
import logging

router = Router()
logger = logging.getLogger(__name__)

def format_bytes(n):
    if n >= 1024**3:
        return f"{n / 1024**3:.2f} GB"
    if n >= 1024**2:
        return f"{n / 1024**2:.2f} MB"
    if n >= 1024:
        return f"{n / 1024:.2f} KB"
    return f"{n} B"

@router.message(F.text == "📊 سرویس من / وضعیت")
async def handle_my_service(message: types.Message):
    user_id = message.from_user.id
    service = database.get_service_for_user(user_id)
    
    if not service:
        await message.answer(
            "📭 شما هنوز سرویس فعالی ندارید.\n\n"
            "برای شروع می‌توانید:\n"
            "• 🧪 تست رایگان ۵۰ مگابایتی بگیرید\n"
            "• 🛒 از فروشگاه پلن تهیه کنید",
            parse_mode="Markdown"
        )
        return
    
    # Fetch live usage from panel
    try:
        live = await sulgx_client.get_link(service["uuid"])
        used_bytes = live.get("used_bytes", 0) if live else 0
    except Exception as e:
        logger.warning(f"Failed to fetch live usage: {e}")
        used_bytes = service.get("used_bytes", 0)
    
    total_bytes = service["volume_gb"] * 1024**3
    remaining = max(total_bytes - used_bytes, 0)
    pct = min(used_bytes / total_bytes * 100, 100) if total_bytes else 0
    
    bar_len = 12
    filled = int(pct / 100 * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)
    
    text = (
        f"📊 **وضعیت سرویس شما**\n\n"
        f"📦 حجم کل: {service['volume_gb']} گیگابایت\n"
        f"📤 مصرف شده: {format_bytes(used_bytes)} ({pct:.1f}%)\n"
        f"📥 حجم باقی‌مانده: {format_bytes(remaining)}\n"
        f"🟩 {bar}\n"
        f"⏰ بازه پیشنهادی: ۳۰ روز استفاده\n\n"
        f"💡 *اگر قبل از اتمام ۳۰ روز، حجم شما تمام شد، از بخش پشتیبانی درخواست کانفیگ جدید با حجم باقی‌مانده را بدهید.*\n\n"
        f"🔗 لینک اتصال شما همان لینک تحویل‌شده است. برای دریافت مجدد، گزینه زیر را انتخاب کنید:"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=service_options_keyboard(service["uuid"]))


@router.callback_query(F.data.startswith("get_vless_"))
async def handle_get_vless(callback: types.CallbackQuery):
    uuid = callback.data.split("_")[-1]
    service = None
    from app.database import get_conn
    with get_conn() as conn:
        service = conn.execute("SELECT * FROM services WHERE uuid=?", (uuid,)).fetchone()
    
    if not service:
        await callback.answer("سرویس یافت نشد")
        return
    
    await callback.message.answer(
        f"🔗 **لینک اتصال VLESS شما:**\n`{service['vless_link']}`\n\n"
        f"📱 این لینک را در v2rayNG (اندروید) یا V2Box (آیفون) کپی و وارد کنید.",
        parse_mode="Markdown"
    )
    await callback.answer("لینک اتصال ارسال شد")


@router.callback_query(F.data.startswith("get_sub_"))
async def handle_get_sub(callback: types.CallbackQuery):
    await callback.answer("لینک سابسکرایب در دسترس نیست — از لینک اصلی VLESS استفاده کنید.", show_alert=True)


@router.callback_query(F.data.startswith("refresh_service_"))
async def handle_refresh_service(callback: types.CallbackQuery):
    uuid = callback.data.split("_")[-1]
    live = await sulgx_client.get_link(uuid)
    if not live:
        await callback.answer("خطا در دریافت وضعیت زنده", show_alert=True)
        return
    
    used = live.get("used_bytes", 0)
    await callback.message.answer(
        f"🔄 **وضعیت لحظه‌ای مصرف:**\n"
        f"📦 مصرف شده: {format_bytes(used)}\n"
        f"✅ سرویس به‌روزرسانی شد",
        parse_mode="Markdown"
    )
    await callback.answer("به‌روزرسانی شد")