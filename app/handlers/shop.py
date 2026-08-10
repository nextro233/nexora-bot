from aiogram import Router, F, types
from app import database, config
from app.keyboards.main import plans_keyboard, payment_methods_keyboard
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
        f"⏳ **کانفیگ شما در حال آماده‌سازی است** (معمولاً چند دقیقه).\n"
        f"پس از آماده شدن، لینک اتصال همین‌جا ارسال می‌شود.\n\n"
        f"💳 *برای تکمیل خرید، مبلغ {plan['stars']} استارز را پرداخت کرده و دکمه پرداخت را بزنید.*"
    )
    await callback.message.edit_text(text, parse_mode="Markdown")
    
    # Notify admin about the new order
    await _notify_admin(callback, order_id, plan)
    
    # Payment buttons — real Stars invoice
    pm_kb = payment_methods_keyboard(order_id, plan["stars"])
    await callback.message.answer(
        f"💳 **پرداخت با استارز تلگرام**\n\n"
        f"سفارش #{order_id} | {plan['gb']} گیگابایت\n"
        f"مبلغ قابل پرداخت: **{plan['stars']} استارز**\n\n"
        f"1️⃣ روی «⭐️ پرداخت با استارز» بزنید\n"
        f"2️⃣ فاکتور رسمی تلگرام باز می‌شود\n"
        f"3️⃣ پرداخت را در تلگرام تأیید کنید\n"
        f"4️⃣ به محض تأیید پرداخت، ادمین کانفیگ را می‌فرستد ✅\n\n"
        f"🔒 *پرداخت مستقیم توسط تلگرام تأیید می‌شود — هیچ ادعای دستی‌ای لازم نیست.*",
        reply_markup=pm_kb, parse_mode="Markdown"
    )
    await callback.answer()


async def _notify_admin(callback: types.CallbackQuery, order_id: int, plan: dict):
    """Send order notification to the admin (owner) for manual config creation."""
    from app.instances import bot
    user = callback.from_user
    username = f"@{user.username}" if user.username else "—"
    
    text = (
        f"🛒 **سفارش جدید #{order_id}**\n\n"
        f"👤 کاربر: {user.first_name}\n"
        f"🆔 آیدی: `{user.id}`\n"
        f"📛 یوزرنیم: {username}\n"
        f"📦 حجم: {plan['gb']} گیگابایت\n"
        f"⭐ قیمت: {plan['stars']} استارز\n"
        f"💵 معادل: {plan['price_toman']:,} تومان\n\n"
        f"⚙️ **برای تحویل:** کانفیگ را بسازید و دستور زیر را بزنید:\n"
        f"`/deliver {order_id}`\n"
        f"سپس لینک VLESS را ارسال کنید."
    )
    try:
        await bot.send_message(config.ADMIN_ID, text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Admin notify failed: {e}")


@router.callback_query(F.data == "cancel_action")
async def handle_cancel_action(callback: types.CallbackQuery):
    await callback.message.answer("عملیات لغو شد.")
    await callback.answer()