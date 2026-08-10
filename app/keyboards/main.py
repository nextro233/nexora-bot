from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from app import config

def main_keyboard():
    kb = [
        [KeyboardButton(text="🛒 خرید سرویس (اکانت)"), KeyboardButton(text="🧪 تست رایگان 50MB")],
        [KeyboardButton(text="📊 سرویس من / وضعیت"), KeyboardButton(text="⭐ آموزش پرداخت استارز")],
        [KeyboardButton(text="📩 گزارش مشکل / پشتیبانی"), KeyboardButton(text="📚 آموزش اتصال")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def plans_keyboard():
    inline_kb = []
    for gb, p in config.PLANS.items():
        btn_text = f"{p['label']} — {p['stars']} ⭐ ({p['price_toman']:,} تومان)"
        inline_kb.append([InlineKeyboardButton(text=btn_text, callback_data=f"buy_plan_{gb}")])
    inline_kb.append([InlineKeyboardButton(text="❌ انصراف", callback_data="cancel_action")])
    return InlineKeyboardMarkup(inline_keyboard=inline_kb)

def payment_methods_keyboard(order_id: int, stars_amount: int):
    kb = [
        [InlineKeyboardButton(text=f"⭐️ پرداخت با استارز ({stars_amount} ⭐)", callback_data=f"pay_stars_{order_id}")],
        [InlineKeyboardButton(text="🔄 وضعیت پرداخت و فعال‌سازی", callback_data=f"check_pay_{order_id}")],
        [InlineKeyboardButton(text="❌ لغو سفارش", callback_data=f"cancel_order_{order_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def service_options_keyboard(uuid: str):
    kb = [
        [InlineKeyboardButton(text="🔗 دریافت مجدد لینک اتصال (VLESS)", callback_data=f"get_vless_{uuid}")],
        [InlineKeyboardButton(text="🔄 بروزرسانی وضعیت مصرف", callback_data=f"refresh_service_{uuid}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)
