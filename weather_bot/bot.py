from __future__ import annotations

import logging
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from weather_bot import config

logger = logging.getLogger(__name__)

router = Router()


def _resolve_webapp_url(base_url: str) -> str | None:
    """Возвращает URL Mini App только если он валидный и HTTPS."""
    if not base_url:
        return None

    normalized = base_url.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.netloc:
        logger.warning(
            "PUBLIC_BASE_URL is not valid HTTPS URL: %r. Mini App button disabled.",
            base_url,
        )
        return None
    return f"{normalized}/"


@router.message(Command("start", "help"))
async def cmd_start(message: Message) -> None:
    url = _resolve_webapp_url(config.PUBLIC_BASE_URL)
    if url:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🌤️ Открыть прогноз",
                        web_app=WebAppInfo(url=url),
                    )
                ]
            ]
        )
        await message.answer(
            "👋 Привет! Нажми кнопку ниже — откроется Mini App с прогнозом погоды.\n"
            "🏙️ Введи город и нажми «Показать прогноз».\n\n"
            "💬 Также можно написать город прямо в чат: например `Москва` или `London`.",
            reply_markup=kb,
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await message.answer(
            "👋 Привет! Напиши в чат название города — например `Москва` или `London`.\n\n"
            "ℹ️ Кнопка Mini App появится, если в `.env` задать `PUBLIC_BASE_URL` (HTTPS) — см. комментарии в файле.",
            parse_mode=ParseMode.MARKDOWN,
        )


@router.message(F.text)
async def city_text(message: Message) -> None:
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return

    if not config.OPENWEATHER_API_KEY:
        await message.answer("⚠️ На сервере не задан `OPENWEATHER_API_KEY`.")
        return

    from weather_bot.weather_service import fetch_forecast

    try:
        data = await fetch_forecast(config.OPENWEATHER_API_KEY, text)
    except ValueError as e:
        await message.answer(f"🔎 {e}")
        return
    except Exception:
        logger.exception("forecast failed")
        await message.answer("😔 Не удалось получить прогноз. Попробуйте чуть позже.")
        return

    loc = data["location"]
    lines = [f"📍 *{loc}*", ""]
    for d in data.get("daily", [])[:5]:
        lines.append(
            f"🗓️ *{d['label']}*: 🌡️ {d['temp_min']}…{d['temp_max']} °C, "
            f"{d['description']}, 💨 ветер до {d['wind_max_ms']} м/с, "
            f"🌧️ осадки до {d['precipitation_prob_max']}%"
        )
    await message.answer("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


def build_dispatcher() -> Dispatcher:
    if not config.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Задайте TELEGRAM_BOT_TOKEN")
    dp = Dispatcher()
    dp.include_router(router)
    return dp


async def run_polling() -> None:
    """Запуск long polling (вызывать из asyncio-задачи рядом с uvicorn)."""
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    dp = build_dispatcher()
    await dp.start_polling(bot, drop_pending_updates=True)
