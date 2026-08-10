from aiogram import Router, F, types
from app import database, config
from app.keyboards.main import plans_keyboard, payment_methods_keyboard
from app.services.sulgx import sulgx_client
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.message(F.text == "🛒 خرید سرویس (اکانت)")
async def handle_buy(message: types.Message):
    text = (
        "🛒 **فروشگاه سرویس NEXORA**\n\n"
        "لطفاً حجم مورد نیاز خود را انتخاب کنید:\n\n"
        "💡 *هرچه حجم بیشتر، قیمت هر گیگابایت پایین‌تر!*\n\n"
        f"💰 قیمت پایه: {config.BASE_PRICE_PER_GB:,} تومان به ازای هر گیگابایت"
    )
    await message.answer(text, reply_markup=plans_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data.startswith("buy_plan_"))
async def handle_buy_plan(callback: types.CallbackQuery):
    gb = int(callback.data.split("_")[-1])
    plan = config.PLANS.get(gb)
    
    if not plan:
        await callback.answer("پلن انتخابی نامعتبر است")
        return
    
    order_id = database.create_order(
        telegram_id=callback.from_user.id,
        plan_gb=plan["gb"],
        price_toman=plan["price_toman"],
        price_stars=plan["stars"]
    )
    
    text = (
        f"🧾 **سفارش #{order_id} ثبت شد**\n\n"
        f"📦 حجم: **{plan['gb']} گیگابایت**\n"
        f"💎 تخفیف: **{plan['discount']}%**\n"
        f"💵 قیمت: **{plan['price_toman']:,} تومان**\n"
        f"⭐ معادل: **{plan['stars']} استارز**\n\n"
        f"🎁 **سرویس شما پیش از پرداخت ساخته شد!**\n"
        f"1️⃣ کانفیگ در پیام بعدی ارسال می‌شود ✨\n"
        f"2️⃣ **۵ دقیقه** فرصت دارید مبلغ استارز را پرداخت کنید.\n"
        f"3️⃣ در صورت عدم پرداخت تا ۵ دقیقه، سرویس خودکار غیرفعال می‌شود."
    )
    await callback.message.edit_text(text, parse_mode="Markdown")
    
    # 1. Create link on SulgX panel immediately
    label = "NEXORA VIP - 24-7 Support - nexorasup_bot"
    res = await sulgx_client.create_link(label=label, limit_gb=plan["gb"])
    
    if not res:
        await callback.message.answer(
            "❌ متأسفانه در ساخت کانفیگ روی سرور خطایی رخ داد.\n"
            "لطفاً دقایقی دیگر دوباره تلاش کنید یا با پشتیبانی تماس بگیرید."
        )
        database.set_order_status(order_id, "failed")
        return

    vless_link = res.get("vless_link", "")
    sub_url = res.get("subscription_url", "")
    uuid = res.get("uuid", "")
    
    # 2. Store service in database
    database.create_service(
        order_id=order_id,
        telegram_id=callback.from_user.id,
        uuid=uuid,
        label=label,
        volume_gb=plan["gb"],
        subscription_url=sub_url,
        vless_link=vless_link,
        expires_at=None
    )
    
    # 3. Deliver config immediately
    delivery_text = (
        f"🚀 **کانفیگ شما آماده و تحویل شد!**\n\n"
        f"🔗 **لینک اتصال (VLESS):**\n"
        f"`{vless_link}`\n\n"
        f"📊 حجم: {plan['gb']} گیگابایت\n\n"
        f"💡 *توصیه:* بهتر است بسته خود را برای **۳۰ روز** استفاده کنید. اگر قبل از ۳۰ روز حجم تمام شد، نگران نباشید — به بخش پشتیبانی اطلاع دهید تا کانفیگ جدید متناسب با حجم باقی‌مانده دریافت کنید.*\n\n"
        f"💳 *برای فعال‌سازی دائمی، لطفاً پرداخت {plan['stars']} استارز را تکمیل کنید.*"
    )
    await callback.message.answer(delivery_text, parse_mode="Markdown")
    
    # 4. Payment button
    pm_kb = payment_methods_keyboard(order_id, plan["stars"])
    await callback.message.answer(
        f"💳 **درگاه پرداخت استارز (مهلت: ۵ دقیقه)**\n\n"
        f"سفارش #{order_id} | {plan['gb']} گیگابایت\n"
        f"مبلغ قابل پرداخت: **{plan['stars']} استارز**",
        reply_markup=pm_kb, parse_mode="Markdown"
    )
    await callback.answer()
    
    # 5. Schedule 5-minute timeout deactivation
    from app.scheduler import schedule_payment_timeout
    schedule_payment_timeout(order_id, uuid)


@router.callback_query(F.data == "cancel_action")
async def handle_cancel_action(callback: types.CallbackQuery):
    await callback.message.answer("عملیات لغو شد.")
    await callback.answer()