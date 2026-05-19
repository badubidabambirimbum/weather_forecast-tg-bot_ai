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
from aiogram.types import BotCommand, MenuButtonWebApp, Message, ReplyKeyboardRemove, WebAppInfo
from dotenv import load_dotenv
from pydantic import ValidationError

from backend.db.engine import check_connection, dispose_engine, init_engine, is_engine_initialized
from backend.db.repository import (
    record_forecast_request_safe,
    upsert_user_safe,
    user_profile_from_aiogram,
)
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
_SERVER_ERROR_PUBLIC = "Unexpected server error"
_FORECAST_VALIDATION_MSG = (
    "Некорректные параметры: город — от 2 до 100 символов, дни только 1, 3 или 10."
)

dp = Dispatcher()


def _is_database_configured() -> bool:
    """True, если задан DATABASE_URL (общий с backend)."""
    return bool(os.getenv("DATABASE_URL", "").strip())


async def _init_bot_database() -> None:
    """Подключает PostgreSQL в процессе бота (отдельно от uvicorn)."""
    if not _is_database_configured():
        logger.warning("DATABASE_URL не задан — бот не пишет в PostgreSQL")
        return
    init_engine()
    if not await check_connection():
        raise RuntimeError("Не удалось подключиться к PostgreSQL (DATABASE_URL)")
    logger.info("PostgreSQL: подключение установлено (бот)")


async def _touch_user(message: Message) -> int | None:
    """Upsert профиля из message.from_user; возвращает telegram_user_id или None."""
    user = message.from_user
    if user is None:
        return None
    try:
        profile = user_profile_from_aiogram(user)
    except ValueError:
        logger.warning("Не удалось разобрать from_user для записи в БД")
        return None
    await upsert_user_safe(profile, source="bot")
    return profile.telegram_user_id


async def _log_and_touch_user(message: Message, label: str) -> int | None:
    """Лог команды и upsert пользователя в БД."""
    _log_command_context(message, label)
    return await _touch_user(message)


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


async def setup_menu_button(bot: Bot, miniapp_url: str) -> None:
    """Настраивает кнопку слева от поля ввода (Menu Button) для запуска Mini App."""
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="Открыть Mini App",
            web_app=WebAppInfo(url=miniapp_url),
        )
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
    """Подсказывает, как открыть Mini App через Menu Button."""
    await _log_and_touch_user(message, "Команда /start")
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
            "Текстовый прогноз доступен: /forecast <город> [1|3|10]",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await message.answer(
        "Откройте Mini App через кнопку слева от поля ввода (Menu Button).\n"
        "Или запросите прогноз здесь: /forecast <город> [1|3|10]",
        reply_markup=ReplyKeyboardRemove(),
    )


@dp.message(Command("help"))
async def handle_help(message: Message) -> None:
    """Краткий список команд бота."""
    await _log_and_touch_user(message, "Команда /help")
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
    await _log_and_touch_user(message, "Команда /about")
    await message.answer(
        "Бот показывает прогноз погоды через Open‑Meteo (без отдельного API‑ключа).\n"
        "Можно открыть Mini App (/start) или получить краткий прогноз командой /forecast."
    )


@dp.message(Command("ping"))
async def handle_ping(message: Message) -> None:
    """Минимальный health-check: ответ «pong»."""
    await _log_and_touch_user(message, "Команда /ping")
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
    telegram_user_id = await _touch_user(message)
    resolved_city: str | None = None

    try:
        ForecastQuery(city=city, days=days)
    except ValidationError:
        logger.info(
            "Команда /forecast: валидация Pydantic user_id=%s chat_id=%s",
            message.from_user.id if message.from_user else None,
            message.chat.id if message.chat else None,
        )
        if telegram_user_id is not None:
            await record_forecast_request_safe(
                telegram_user_id=telegram_user_id,
                source="bot",
                query_city=city,
                days=days,
                status="validation_error",
                error_detail=_FORECAST_VALIDATION_MSG,
            )
        await message.answer(_FORECAST_VALIDATION_MSG)
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
        if telegram_user_id is not None:
            await record_forecast_request_safe(
                telegram_user_id=telegram_user_id,
                source="bot",
                query_city=city,
                days=days,
                status="open_meteo_error",
                resolved_city=resolved_city,
                error_detail=str(exc),
            )
        await message.answer(str(exc) or "Не удалось получить прогноз.")
        return
    except Exception:
        logger.exception(
            "Команда /forecast: непредвиденная ошибка user_id=%s chat_id=%s",
            message.from_user.id if message.from_user else None,
            message.chat.id if message.chat else None,
        )
        if telegram_user_id is not None:
            await record_forecast_request_safe(
                telegram_user_id=telegram_user_id,
                source="bot",
                query_city=city,
                days=days,
                status="server_error",
                resolved_city=resolved_city,
                error_detail=_SERVER_ERROR_PUBLIC,
            )
        await message.answer("Внутренняя ошибка. Попробуйте позже.")
        return

    if telegram_user_id is not None:
        await record_forecast_request_safe(
            telegram_user_id=telegram_user_id,
            source="bot",
            query_city=city,
            days=days,
            status="success",
            resolved_city=resolved_city,
        )
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
    await _log_and_touch_user(message, f"Неизвестная команда {cmd}")
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
    await _touch_user(message)
    await message.answer(
        "Напишите команду, например /help или /forecast Москва.\n"
        "Или откройте Mini App: /start"
    )


async def main() -> None:
    """Точка входа: настройка меню команд и long-polling Telegram-бота."""
    logger.info("Запуск Telegram-бота (long polling)")
    bot = Bot(token=BOT_TOKEN)
    try:
        await _init_bot_database()
        await setup_bot_commands(bot)
        miniapp_url = resolve_miniapp_url(MINIAPP_URL)
        if miniapp_url:
            await setup_menu_button(bot, miniapp_url)
            logger.info("Menu Button Mini App включен")
        else:
            logger.warning("Menu Button Mini App не включен: MINIAPP_URL невалидный или не HTTPS")
        await dp.start_polling(bot, drop_pending_updates=True)
    except Exception:
        logger.exception("Ошибка во время работы polling")
        raise
    finally:
        if is_engine_initialized():
            await dispose_engine()
        await bot.session.close()
        logger.info("Polling остановлен, HTTP-сессия бота закрыта")


if __name__ == "__main__":
    asyncio.run(main())
