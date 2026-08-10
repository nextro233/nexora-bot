"""Real Telegram Stars (XTR) payment via sendInvoice.
No more fake "I paid" buttons — Telegram confirms the payment itself.
"""
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import LabeledPrice
from app import database, config
import logging

router = Router()
logger = logging.getLogger(__name__)

class PaymentStates(StatesGroup):
    awaiting_payment = State()


@router.callback_query(F.data.startswith("pay_stars_"))
async def handle_pay_stars(callback: types.CallbackQuery, state: FSMContext):
    """Send a real Telegram Stars invoice to the customer."""
    order_id = int(callback.data.split("_")[-1])
    order = database.get_order(order_id)
    if not order:
        await callback.answer("سفارش یافت نشد")
        return

    if order["status"] in ("paid", "active"):
        await callback.answer("✅ این سفارش قبلاً پرداخت شده است.")
        return

    plan_gb = order["plan_gb"]
    stars = order["price_stars"]

    title = f"کانفیگ NEXORA {plan_gb} گیگابایت"
    description = (
        f"سفارش #{order_id} — {plan_gb} گیگابایت\n"
        f"پس از پرداخت، ادمین کانفیگ را برای شما ارسال می‌کند."
    )

    try:
        await callback.message.answer_invoice(
            title=title,
            description=description,
            payload=f"order_{order_id}",
            currency="XTR",  # Telegram Stars
            prices=[LabeledPrice(label="سرویس VPN (کانفیگ)", amount=stars)],
            provider_token="",  # required empty for XTR
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Invoice failed: {e}")
        await callback.answer("خطا در ایجاد فاکتور. دوباره تلاش کنید.", show_alert=True)


@router.pre_checkout_query()
async def handle_pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    """Must answer OK for the payment to go through."""
    payload = pre_checkout_query.invoice_payload or ""
    order_id = int(payload.replace("order_", "")) if payload.startswith("order_") else None
    if order_id is None:
        await pre_checkout_query.answer(ok=False, error_message="فاکتور نامعتبر است.")
        return
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def handle_successful_payment(message: types.Message):
    """Called ONLY when Telegram confirms real payment. No fake claims possible."""
    payment = message.successful_payment
    payload = payment.invoice_payload or ""
    order_id = int(payload.replace("order_", "")) if payload.startswith("order_") else None
    stars_amount = payment.total_amount  # in stars (XTR units = stars directly)
    currency = payment.currency  # XTR
    charge_id = payment.telegram_payment_charge_id

    if order_id is None:
        await message.answer("⚠️ فاکتور نامعتبر است. لطفاً به پشتیبانی پیام دهید.")
        return

    order = database.get_order(order_id)
    if not order:
        await message.answer("سفارش یافت نشد. به پشتیبانی پیام دهید.")
        return

    # Mark as paid with the real charge id
    database.set_order_status(order_id, "paid", payment_charge_id=charge_id)

    # Confirm to the customer
    await message.answer(
        f"✅ **پرداخت با موفقیت انجام شد!**\n\n"
        f"🧾 سفارش #{order_id} | {order['plan_gb']} گیگابایت\n"
        f"⭐ مبلغ: **{stars_amount} استارز**\n\n"
        f"🛠 در حال آماده‌سازی کانفیگ شما هستیم — به‌زودی ارسال می‌شود.\n"
        f"معمولاً چند دقیقه طول می‌کشد.",
        parse_mode="Markdown"
    )

    # Notify admin with REAL payment proof
    user = message.from_user
    username = f"@{user.username}" if user.username else "—"
    try:
        from app.instances import bot
        await bot.send_message(
            config.ADMIN_ID,
            f"💰 **پرداخت واقعی استارز دریافت شد!**\n\n"
            f"🧾 سفارش #{order_id} | {order['plan_gb']} گیگابایت\n"
            f"⭐ مبلغ: **{stars_amount} XTR (استارز)**\n"
            f"🆔 Charge ID: `{charge_id}`\n\n"
            f"👤 مشتری: {user.first_name} ({username})\n"
            f"🆔 آیدی: `{user.id}`\n\n"
            f"⚙️ حالا کانفیگ را بسازید و تحویل دهید:\n"
            f"`/deliver {order_id}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Admin payment notify failed: {e}")


@router.callback_query(F.data.startswith("cancel_order_"))
async def handle_cancel_order(callback: types.CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[-1])
    order = database.get_order(order_id)
    if not order:
        await callback.answer("سفارش یافت نشد")
        return

    database.set_order_status(order_id, "cancelled")
    await callback.message.answer("❌ سفارش لغو شد. در صورت تمایل می‌توانید دوباره از فروشگاه خرید کنید.")
    await callback.answer()
    await state.clear()


@router.callback_query(F.data.startswith("check_pay_"))
async def handle_check_payment(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[-1])
    order = database.get_order(order_id)
    if not order:
        await callback.answer("سفارش یافت نشد")
        return

    status_map = {
        "pending": "🟡 در انتظار پرداخت",
        "paid": "🟢 پرداخت تأیید شده — در حال آماده‌سازی کانفیگ",
        "active": "✅ فعال",
        "cancelled": "❌ لغو شده",
        "failed": "⚠️ خطا در ساخت",
        "delivered": "📦 تحویل شده",
    }
    await callback.answer("بررسی وضعیت سفارش", show_alert=False)
    await callback.message.answer(
        f"📦 سفارش #{order_id} | {order['plan_gb']} گیگابایت\n"
        f"وضعیت: {status_map.get(order['status'], order['status'])}",
        parse_mode="Markdown"
    )