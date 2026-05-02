from __future__ import annotations

import asyncio
import logging
import os
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def get_required_env(name: str) -> str:
    """Читает обязательную переменную окружения и валидирует ее."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


BOT_TOKEN = get_required_env("BOT_TOKEN")
MINIAPP_URL = os.getenv("MINIAPP_URL", "").strip()

dp = Dispatcher()


def resolve_miniapp_url(raw_url: str) -> str | None:
    """Проверяет и нормализует URL Mini App.

    Mini App должен открываться по публичному HTTPS URL.
    Возвращает нормализованный URL или None, если URL невалидный.
    """
    if not raw_url:
        return None
    normalized = raw_url.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    return normalized


def webapp_keyboard(miniapp_url: str) -> ReplyKeyboardMarkup:
    """Создает клавиатуру с кнопкой открытия Telegram Mini App."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="Открыть mini app",
                    web_app=WebAppInfo(url=miniapp_url),
                )
            ]
        ],
        resize_keyboard=True,
    )


@dp.message(CommandStart())
async def handle_start(message: Message) -> None:
    """Отправляет пользователю кнопку для запуска Mini App."""
    miniapp_url = resolve_miniapp_url(MINIAPP_URL)
    if miniapp_url is None:
        parsed = urlparse(MINIAPP_URL.strip()) if MINIAPP_URL else None
        logger.warning(
            "MINIAPP_URL не задан или не HTTPS: scheme=%s host=%s",
            (parsed.scheme if parsed else ""),
            (parsed.netloc if parsed else ""),
        )
        await message.answer(
            "Mini App URL пока не настроен. Задайте публичный HTTPS URL в MINIAPP_URL и перезапустите бота."
        )
        return

    user = message.from_user
    chat = message.chat
    logger.info(
        "Команда /start: user_id=%s chat_id=%s",
        user.id if user else None,
        chat.id if chat else None,
    )
    await message.answer(
        "Нажмите кнопку ниже, чтобы открыть Mini App и запросить прогноз.",
        reply_markup=webapp_keyboard(miniapp_url),
    )


async def main() -> None:
    """Точка входа: запускает long-polling Telegram-бота."""
    logger.info("Запуск Telegram-бота (long polling)")
    bot = Bot(token=BOT_TOKEN)
    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    except Exception:
        logger.exception("Ошибка во время работы polling")
        raise
    finally:
        await bot.session.close()
        logger.info("Polling остановлен, HTTP-сессия бота закрыта")


if __name__ == "__main__":
    asyncio.run(main())
