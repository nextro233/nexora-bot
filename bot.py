import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app import config
from app.scheduler import start_scheduler
from app.handlers import start, test, shop, payment, service, support, admin

logging.basicConfig(level=logging.INFO)

# --- Startup validation with clear error messages (for Railway debugging) ---
def _validate_config():
    errors = []
    if not config.BOT_TOKEN:
        errors.append("BOT_TOKEN is EMPTY. Add it in Railway: Project > Variables > BOT_TOKEN=<your token>")
    elif len(config.BOT_TOKEN) < 40 or ":" not in config.BOT_TOKEN:
        errors.append(f"BOT_TOKEN looks malformed (got {len(config.BOT_TOKEN)} chars). Copy the FULL token from @BotFather — no spaces, no quotes.")
    if not config.ADMIN_ID or config.ADMIN_ID == 0:
        errors.append("ADMIN_ID is missing or 0. Add your numeric Telegram ID in Railway Variables.")
    # SulgX config checks
    if not config.SULGX_PASSWORD:
        errors.append("SULGX_PASSWORD is empty — the panel login needs it.")
    if errors:
        raise SystemExit("\n".join(["❌ CONFIG ERRORS (fix these in Railway Variables):"] + [f"  • {e}" for e in errors]))

_validate_config()

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

dp.include_router(start.router)
dp.include_router(test.router)
dp.include_router(shop.router)
dp.include_router(payment.router)
dp.include_router(service.router)
dp.include_router(support.router)
dp.include_router(admin.router)

async def main():
    from app.database import init_db
    init_db()
    start_scheduler()
    print("🤖 NEXORA Bot started!")
    # Delete webhook in case set
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())