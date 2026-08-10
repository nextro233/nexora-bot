from aiogram import Router, F, types
from app import database, config
from app.services.sulgx import sulgx_client
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.message(F.text == "🧪 تست رایگان 50MB")
async def handle_free_test(message: types.Message):
    user_id = message.from_user.id
    
    if not database.can_use_test(user_id):
        await message.answer("❌ شما قبلاً از تست رایگان 50 مگابایتی استفاده کرده‌اید.\nبرای ادامه می‌توانید از بخش '🛒 خرید سرویس' پلن مورد نظر خود را تهیه کنید.")
        return

    msg = await message.answer("⏳ در حال ساخت اکانت تست ۵۰ مگابایتی برای شما...")
    
    label = "NEXORA FREE TEST"
    limit_gb = config.FREE_TEST_MB / 1024.0
    if limit_gb < 0.1:
        limit_gb = 0.05
    res = await sulgx_client.create_link(label=label, limit_gb=limit_gb)
    
    if not res:
        await msg.edit_text("❌ متأسفانه در ساخت اکانت تست خطایی رخ داد. لطفاً دقایقی دیگر دوباره تلاش کنید یا به پشتیبانی اطلاع دهید.")
        return

    vless_link = res.get("vless_link", "")
    sub_url = res.get("subscription_url", "")
    
    database.mark_test_used(user_id, limit_bytes)
    
    response_text = (
        f"✅ **اکانت تست ۵۰ مگابایتی شما با موفقیت ساخته شد!**\n\n"
        f"📦 **حجم:** ۵۰ مگابایت\n"
        f"⚡ **سرعت:** نامحدود و بدون فیلترینگ\n\n"
        f"🔗 **لینک اتصال (VLESS):**\n`{vless_link}`\n\n"
        f"💡 *برای استفاده، لینک بالا را در برنامه v2rayNG (اندروید) یا V2Box (آیفون) وارد کنید.*"
    )
    
    await msg.edit_text(response_text, parse_mode="Markdown")
