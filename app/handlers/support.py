from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from app import database, config
import logging

router = Router()
logger = logging.getLogger(__name__)

class SupportStates(StatesGroup):
    waiting_for_ticket = State()

@router.message(F.text == "📩 گزارش مشکل / پشتیبانی")
async def handle_support_start(message: types.Message, state: FSMContext):
    text = (
        "📩 **پشتیبانی NEXORA**\n\n"
        "لطفاً مشکل خود را بنویسید. مثال:\n\n"
        "• کانفیگ من کار نمی‌کند\n"
        "• حجم به درستی کسر نمی‌شود\n"
        "• سرعت کانفیگ پایین است\n"
        "• قبل از اتمام حجم، کانفیگ از کار افتاده\n\n"
        "*(پیام شما به صورت تیکت برای ادمین ثبت می‌شود و در اسرع وقت رسیدگی می‌شود)*"
    )
    await message.answer(text, parse_mode="Markdown")
    await state.set_state(SupportStates.waiting_for_ticket)

@router.message(SupportStates.waiting_for_ticket)
async def handle_ticket_message(message: types.Message, state: FSMContext):
    # Skip if it's a command or menu button
    if message.text and message.text.startswith("/"):
        await state.clear()
        await message.answer("ثبت تیکت لغو شد.")
        return

    subject = "گزارش مشکل"
    ticket_id = database.create_ticket(
        telegram_id=message.from_user.id,
        subject=subject,
        message=message.text or "[attachment]"
    )
    
    # Notify admin
    try:
        from bot import bot
        await bot.send_message(
            config.ADMIN_ID,
            f"🎫 **تیکت جدید #{ticket_id}**\n\n"
            f"👤 کاربر: {message.from_user.id}\n"
            f"👤 نام: {message.from_user.first_name}\n"
            f"📝 متن:\n{message.text}\n\n"
            f"برای پاسخ، به این کاربر در تلگرام پیام دهید.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")
    
    await message.answer(
        f"✅ **تیکت شما با شماره #{ticket_id} ثبت شد.**\n\n"
        f"کارشناسان ما در کوتاه‌ترین زمان ممکن مشکل شما را بررسی می‌کنند.\n"
        f"برای پیگیری می‌توانید از همین گفتگو پیام بدهید.",
        parse_mode="Markdown"
    )
    await state.clear()