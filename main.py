"""
Запуск HTTP-сервера (Mini App + API) и Telegram-бота (aiogram polling).

Рабочая директория при запуске — корень репозитория (рядом с этим файлом и environment.yml).

Окружение conda: см. environment.yml (Python 3.11).
Переменные окружения: см. .env.example
"""

from __future__ import annotations

import asyncio
import logging
import os

import uvicorn

from weather_bot import config

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)


async def _serve_http(host: str, port: int) -> None:
    from weather_bot.app import create_app

    app = create_app()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="info",
        )
    )
    await server.serve()


async def _async_main() -> None:
    from weather_bot.bot import run_polling

    host = os.getenv("HOST", "0.0.0.0").strip()
    port = int(os.getenv("PORT", "8000"))

    await asyncio.gather(
        _serve_http(host, port),
        run_polling(),
    )


def main() -> None:
    missing = []
    if not config.TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not config.OPENWEATHER_API_KEY:
        missing.append("OPENWEATHER_API_KEY")
    if missing:
        raise SystemExit(
            "Задайте в .env: " + ", ".join(missing) + " (см. .env.example)"
        )

    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
