import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app import config
from app.scheduler import start_scheduler
from app.handlers import start, test, shop, payment, service, support, admin

logging.basicConfig(level=logging.INFO)

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