"""Shared bot/dispatcher instances — avoids circular imports and double-execution of bot.py."""
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app import config

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())