from __future__ import annotations

import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo
from dotenv import load_dotenv

load_dotenv()


def get_required_env(name: str) -> str:
    """Читает обязательную переменную окружения и валидирует ее."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


BOT_TOKEN = get_required_env("BOT_TOKEN")
MINIAPP_URL = get_required_env("MINIAPP_URL")

dp = Dispatcher()


def webapp_keyboard() -> ReplyKeyboardMarkup:
    """Создает клавиатуру с кнопкой открытия Telegram Mini App."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="Открыть mini app",
                    web_app=WebAppInfo(url=MINIAPP_URL),
                )
            ]
        ],
        resize_keyboard=True,
    )


@dp.message(CommandStart())
async def handle_start(message: Message) -> None:
    """Отправляет пользователю кнопку для запуска Mini App."""
    await message.answer(
        "Нажмите кнопку ниже и проверьте mock-ответ mini app.",
        reply_markup=webapp_keyboard(),
    )


async def main() -> None:
    """Точка входа: запускает long-polling Telegram-бота."""
    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
