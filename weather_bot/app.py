from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from weather_bot import config
from weather_bot.telegram_webapp import verify_init_data
from weather_bot.weather_service import fetch_forecast

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class WeatherRequest(BaseModel):
    city: str = Field(min_length=1, max_length=120)
    init_data: str | None = None
    client_debug: dict | None = None


def create_app() -> FastAPI:
    app = FastAPI(title="Weather Mini App API")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/api/weather")
    async def weather(body: WeatherRequest):
        logger.info(
            "weather request: init_data_len=%s client_debug=%s",
            len(body.init_data) if body.init_data else 0,
            body.client_debug,
        )
        city = body.city.strip()
        if not city:
            raise HTTPException(status_code=400, detail="Укажите город")

        if not config.OPENWEATHER_API_KEY:
            raise HTTPException(status_code=503, detail="Не настроен OPENWEATHER_API_KEY")

        if body.init_data:
            try:
                verify_init_data(body.init_data, config.TELEGRAM_BOT_TOKEN)
            except ValueError as e:
                logger.warning("initData verify failed: %s", e)
                raise HTTPException(status_code=401, detail="Недействительные данные Telegram") from e
        elif not config.ALLOW_UNVERIFIED_MINI_APP:
            logger.warning("initData is missing; rejected request")
            raise HTTPException(
                status_code=401,
                detail="Нужны данные Telegram Mini App (init_data). Откройте приложение из кнопки в чате Telegram.",
            )

        try:
            data = await fetch_forecast(config.OPENWEATHER_API_KEY, city)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            logger.exception("weather fetch failed")
            raise HTTPException(status_code=502, detail="Сервис погоды недоступен") from e

        return data

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @app.get("/")
        async def index():
            return FileResponse(STATIC_DIR / "index.html")

    return app
