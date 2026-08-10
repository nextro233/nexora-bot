from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from app import database, config
from app.keyboards.main import payment_methods_keyboard
from app.services.sulgx import sulgx_client
import logging

router = Router()
logger = logging.getLogger(__name__)

class PaymentStates(StatesGroup):
    awaiting_payment = State()


@router.callback_query(F.data.startswith("pay_stars_"))
async def handle_pay_stars(callback: types.CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[-1])
    order = database.get_order(order_id)
    if not order:
        await callback.answer("سفارش یافت نشد")
        return

    plan_gb = order["plan_gb"]
    stars = order["price_stars"]

    text = (
        f"⭐️ **پرداخت با تلگرام استارز**\n\n"
        f"سفارش #{order_id} | {plan_gb} گیگابایت\n\n"
        f"برای پرداخت روی دکمه زیر بزنید مبلغ **{stars} استارز**:\n\n"
        f"**راه‌های تأمین استارز:**\n"
        f"1️⃣ از ربات فروش استارز: {config.STARZ_BOT_USERNAME}\n"
        f"2️⃣ از طریق بخش Stars در تلگرام\n"
    )
    # Build an inline payment attempt (manual acknowledgment flow)
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ پرداخت {stars} استارز انجام شد", callback_data=f"confirm_pay_{order_id}")],
        [InlineKeyboardButton(text="❌ انصراف", callback_data=f"cancel_order_{order_id}")]
    ])
    await callback.message.answer(text, reply_markup=confirm_kb, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_pay_"))
async def handle_confirm_payment(callback: types.CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[-1])
    order = database.get_order(order_id)
    if not order:
        await callback.answer("سفارش یافت نشد")
        return

    if order["status"] == "active":
        await callback.answer("✅ این سفارش قبلاً پرداخت و فعال شده است.")
        return

    # Mark payment as received (user confirmed; admin should verify manually)
    database.set_order_status(order_id, "payment_received")
    database.clear_deferred_payment(order_id)

    text = (
        f"✅ **پرداخت ثبت شد — سرویس شما فعال است!**\n\n"
        f"🎉 ممنون از خرید شما!\n"
        f"سفارش #{order_id} نهایی شد.\n\n"
        f"🔗 لینک کانفیگ شما در پیام قبلی ارسال شد.\n"
        f"📊 برای مشاهده وضعیت سرویس از منوی «📊 سرویس من / وضعیت» دکمه بزنید.\n\n"
        f"💚 از اعتماد شما سپاسگزاریم — NEXORA"
    )
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()
    await state.clear()


@router.callback_query(F.data.startswith("cancel_order_"))
async def handle_cancel_order(callback: types.CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[-1])
    order = database.get_order(order_id)
    if not order:
        await callback.answer("سفارش یافت نشد")
        return

    # Find and deactivate service
    try:
        from app.services.sulgx import sulgx_client
        service = database.get_service_for_user(callback.from_user.id)
        if service:
            await sulgx_client.set_link_status(service["uuid"], active=False)
            database.deactivate_service(service["uuid"])
    except Exception as e:
        logger.error(f"Cancel order service deactivation failed: {e}")

    database.set_order_status(order_id, "cancelled")
    await callback.message.answer("❌ سفارش لغو شد. سرویس مربوطه غیرفعال گردید.\nدر صورت تمایل می‌توانید دوباره از فروشگاه خرید کنید.")
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
        "payment_received": "🟢 پرداخت ثبت شده — در حال بررسی و فعال‌سازی",
        "active": "✅ فعال",
        "cancelled": "❌ لغو شده",
        "failed": "⚠️ خطا در ساخت"
    }
    await callback.answer("بررسی وضعیت سفارش", show_alert=False)
    await callback.message.answer(
        f"📦 سفارش #{order_id} | {order['plan_gb']} گیگابایت\n"
        f"وضعیت: {status_map.get(order['status'], order['status'])}",
        parse_mode="Markdown"
    )