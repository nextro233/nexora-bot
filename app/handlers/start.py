from aiogram import Router, F, types
from aiogram.filters import CommandStart
from app import database, config
from app.keyboards.main import main_keyboard

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    user = database.create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username or "",
        first_name=message.from_user.first_name or ""
    )
    
    welcome_text = (
        f"👋 سلام {message.from_user.first_name} عزیز!\n\n"
        f"به **NEXORA VPN** خوش آمدید ⚡\n\n"
        f"ارائه‌دهنده سرویس‌های حجمی اختصاصی VLESS با بالاترین سرعت و پایداری.\n\n"
        f"✨ **ویژگی‌های NEXORA:**\n"
        f"• 🧪 تست رایگان ۵۰ مگابایتی برای تست سرعت و کیفیت\n"
        f"• 🚀 تحویل سریع کانفیگ پیش از پرداخت جهت اطمینان شما\n"
        f"• ⭐ پرداخت آسان با تلگرام استارز (Stars)\n"
        f"• 📊 مشاهده حجم باقی‌مانده آنلاین در ربات\n\n"
        f"💡 *نکته:* پیشنهاد می‌شود بسته‌ها را برای **۳۰ روز** استفاده کنید. در صورت اتمام زودتر از موعد، می‌توانید با ارسال پیام به پشتیبانی، کانفیگ جدید متناسب با حجم باقی‌مانده دریافت کنید.\n\n"
        f"از منوی زیر گزینه مورد نظر خود را انتخاب کنید:"
    )
    await message.answer(welcome_text, reply_markup=main_keyboard(), parse_mode="Markdown")

@router.message(F.text == "⭐ آموزش پرداخت استارز")
async def cmd_help_stars(message: types.Message):
    text = (
        "⭐ **راهنمای خرید و پرداخت استارز (Telegram Stars):**\n\n"
        "1️⃣ **چرا استارز؟**\n"
        "پرداخت با استارز کاملاً امن و درون‌برنامه‌ای است و نیاز به وارد کردن شماره کارت ندارد.\n\n"
        "2️⃣ **چگونه استارز تهیه کنیم؟**\n"
        "می‌توانید عبارت **«خرید استارز تلگرام»** را در تلگرام یا گوگل جستجو کنید و از منابع یا وب‌سایت‌های معتبر (مانند ایرانی کارت یا ربات‌های واسط) استارز مورد نیاز خود را تهیه فرمایید.\n\n"
        "3️⃣ **مراحل خرید در NEXORA:**\n"
        "• پلن مورد نظر خود را انتخاب کنید.\n"
        "• کانفیگ اختصاصی شما ساخته شده و تحویل داده می‌شود (فرصت ۵ دقیقه‌ای پرداخت).\n"
        "• پرداخت را انجام داده و دکمه تایید پرداخت را بزنید تا سرویس شما فعال بماند."
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(F.text == "📚 آموزش اتصال")
async def cmd_help_connect(message: types.Message):
    text = (
        "📚 **راهنمای اتصال به کانفیگ‌های NEXORA:**\n\n"
        "📱 **اندروید (Android):**\n"
        "برنامه پیشنهادی: `v2rayNG` یا `v2rayN`\n"
        "لینک VLESS را کپی کرده و در برنامه گزینه Import from Clipboard را بزنید.\n\n"
        "🍏 **آیفون (iOS):**\n"
        "برنامه‌های پیشنهادی: `Streisand` یا `V2Box` یا `FoXray`\n"
        "لینک VLESS را کپی کرده و در برنامه وارد کنید.\n\n"
        "💻 **ویندوز (Windows):**\n"
        "برنامه پیشنهادی: `v2rayN` یا `NekoBox`\n\n"
        "💡 *توصیه:* بسته‌های حجمی را طوری مدیریت کنید که در ۳۰ روز استفاده شوند."
    )
    await message.answer(text, parse_mode="Markdown")