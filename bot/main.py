from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

# Запуск `python bot/main.py`: каталог скрипта в sys.path[0], пакеты `backend` и `bot` — из корня репозитория.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import BotCommand, KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo
from dotenv import load_dotenv
from pydantic import ValidationError

from backend.schemas import ForecastQuery
from backend.services.open_meteo import OpenMeteoClient, OpenMeteoError
from bot.forecast_args import format_forecast_text, parse_forecast_args

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


def _log_command_context(message: Message, label: str) -> None:
    """Пишет в лог user_id и chat_id для диагностики команд и сообщений."""
    user = message.from_user
    chat = message.chat
    logger.info(
        "%s: user_id=%s chat_id=%s",
        label,
        user.id if user else None,
        chat.id if chat else None,
    )


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


async def setup_bot_commands(bot: Bot) -> None:
    """Регистрирует пункты меню команд Telegram (подсказка для пользователя)."""
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Открыть Mini App"),
            BotCommand(command="help", description="Список команд"),
            BotCommand(command="about", description="О боте и данных"),
            BotCommand(command="ping", description="Проверка, что бот отвечает"),
            BotCommand(command="forecast", description="Прогноз в чат: город [1|3|10]"),
        ]
    )


@dp.message(CommandStart())
async def handle_start(message: Message) -> None:
    """Отправляет пользователю кнопку для запуска Mini App."""
    _log_command_context(message, "Команда /start")
    miniapp_url = resolve_miniapp_url(MINIAPP_URL)
    if miniapp_url is None:
        parsed = urlparse(MINIAPP_URL.strip()) if MINIAPP_URL else None
        logger.warning(
            "MINIAPP_URL не задан или не HTTPS: scheme=%s host=%s",
            (parsed.scheme if parsed else ""),
            (parsed.netloc if parsed else ""),
        )
        await message.answer(
            "Mini App URL пока не настроен. Задайте публичный HTTPS URL в MINIAPP_URL и перезапустите бота.\n"
            "Текстовый прогноз доступен: /forecast <город> [1|3|10]"
        )
        return

    await message.answer(
        "Нажмите кнопку ниже, чтобы открыть Mini App и запросить прогноз.\n"
        "Или запросите прогноз здесь: /forecast <город> [1|3|10]",
        reply_markup=webapp_keyboard(miniapp_url),
    )


@dp.message(Command("help"))
async def handle_help(message: Message) -> None:
    """Краткий список команд бота."""
    _log_command_context(message, "Команда /help")
    text = (
        "Доступные команды:\n"
        "/start — открыть Mini App (кнопка WebApp)\n"
        "/forecast <город> [1|3|10] — прогноз текстом в чате (дней по умолчанию 3)\n"
        "/about — откуда данные и что умеет бот\n"
        "/ping — проверка ответа\n"
        "/help — это сообщение"
    )
    await message.answer(text)


@dp.message(Command("about"))
async def handle_about(message: Message) -> None:
    """Назначение бота и источник данных."""
    _log_command_context(message, "Команда /about")
    await message.answer(
        "Бот показывает прогноз погоды через Open‑Meteo (без отдельного API‑ключа).\n"
        "Можно открыть Mini App (/start) или получить краткий прогноз командой /forecast."
    )


@dp.message(Command("ping"))
async def handle_ping(message: Message) -> None:
    """Минимальный health-check: ответ «pong»."""
    _log_command_context(message, "Команда /ping")
    await message.answer("pong")


@dp.message(Command("forecast"))
async def handle_forecast(message: Message, command: CommandObject) -> None:
    """Текстовый прогноз в чате через тот же клиент Open‑Meteo, что и backend."""
    _log_command_context(message, "Команда /forecast")
    parsed = parse_forecast_args(command.args)
    if parsed is None:
        await message.answer(
            "Использование: /forecast <город> [1|3|10]\n"
            "Примеры: /forecast Москва\n"
            "/forecast Санкт-Петербург 10\n"
            "Если число дней не указать — берётся 3."
        )
        return

    city, days = parsed
    try:
        ForecastQuery(city=city, days=days)
    except ValidationError:
        logger.info(
            "Команда /forecast: валидация Pydantic user_id=%s chat_id=%s",
            message.from_user.id if message.from_user else None,
            message.chat.id if message.chat else None,
        )
        await message.answer(
            "Некорректные параметры: город — от 2 до 100 символов, дни только 1, 3 или 10."
        )
        return

    client = OpenMeteoClient()
    try:
        lat, lon, resolved_city = await client.get_city_coordinates(city)
        points = await client.get_daily_forecast(lat=lat, lon=lon, days=days)
    except OpenMeteoError as exc:
        logger.warning(
            "Команда /forecast: Open-Meteo user_id=%s chat_id=%s detail=%s",
            message.from_user.id if message.from_user else None,
            message.chat.id if message.chat else None,
            exc,
        )
        await message.answer(str(exc) or "Не удалось получить прогноз.")
        return
    except Exception:
        logger.exception(
            "Команда /forecast: непредвиденная ошибка user_id=%s chat_id=%s",
            message.from_user.id if message.from_user else None,
            message.chat.id if message.chat else None,
        )
        await message.answer("Внутренняя ошибка. Попробуйте позже.")
        return

    text = format_forecast_text(resolved_city, days, points)
    await message.answer(text)


@dp.message(F.text.startswith("/"))
async def handle_unknown_command(message: Message) -> None:
    """Неизвестные команды вида /foo — подсказка вместо молчания.

    Регистрируется после всех `Command(...)`, чтобы не перехватывать известные команды.
    """
    if not message.text:
        return
    cmd = message.text.split()[0].split("@")[0].lower()
    _log_command_context(message, f"Неизвестная команда {cmd}")
    await message.answer(
        "Неизвестная команда. Список: /help\n"
        "Прогноз в удобном виде — /start (Mini App) или /forecast <город>."
    )


@dp.message(F.text, ~F.text.startswith("/"))
async def handle_plain_text(message: Message) -> None:
    """Обычный текст без / — подсказка, чтобы не оставлять пользователя без ответа."""
    text = message.text or ""
    preview = text.strip()[:80]
    logger.info(
        "Сообщение без команды: user_id=%s chat_id=%s text_len=%s preview=%r",
        message.from_user.id if message.from_user else None,
        message.chat.id if message.chat else None,
        len(text),
        preview,
    )
    await message.answer(
        "Напишите команду, например /help или /forecast Москва.\n"
        "Или откройте Mini App: /start"
    )


async def main() -> None:
    """Точка входа: настройка меню команд и long-polling Telegram-бота."""
    logger.info("Запуск Telegram-бота (long polling)")
    bot = Bot(token=BOT_TOKEN)
    try:
        await setup_bot_commands(bot)
        await dp.start_polling(bot, drop_pending_updates=True)
    except Exception:
        logger.exception("Ошибка во время работы polling")
        raise
    finally:
        await bot.session.close()
        logger.info("Polling остановлен, HTTP-сессия бота закрыта")


if __name__ == "__main__":
    asyncio.run(main())
