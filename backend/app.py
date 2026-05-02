from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from backend.schemas import ForecastQuery, ForecastResponse
from backend.services.open_meteo import OpenMeteoClient, OpenMeteoError

# Единый ответ для этапа проверки интеграции Mini App.
MOCK_MESSAGE = "Здесь скоро появится прогноз погоды, следите за новостями:)"
load_dotenv()

logger = logging.getLogger(__name__)

# Путь к статическим файлам Mini App (HTML/CSS/JS).
MINIAPP_DIR = Path(__file__).resolve().parent.parent / "miniapp"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Настройка логирования пакета backend при старте приложения (uvicorn)."""
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    for log_name in ("backend", "backend.app", "backend.services", "backend.services.open_meteo"):
        logging.getLogger(log_name).setLevel(level)
    logger.info("Backend запущен: LOG_LEVEL=%s", level_name)
    yield
    logger.info("Backend останавливается")


# Инициализация backend приложения.
app = FastAPI(
    title="Weather Mini App Backend",
    description="Каркас backend для шага 1: проверка интеграции Telegram Mini App.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def log_http_requests(request: Request, call_next):
    """Краткий access-log без тела запроса и без query string (меньше шума и PII)."""
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s -> %s (%.1f ms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


def build_open_meteo_client() -> OpenMeteoClient:
    """Создает клиент Open-Meteo (без API-ключа)."""
    return OpenMeteoClient()


@app.get("/health")
async def healthcheck() -> dict[str, bool]:
    """Проверка, что backend запущен и отвечает."""
    return {"ok": True}


@app.get("/api/mock")
async def mock_message() -> JSONResponse:
    """Тестовый endpoint для кнопки в Mini App на шаге 1."""
    return JSONResponse(content={"message": MOCK_MESSAGE})


@app.get("/api/forecast", response_model=ForecastResponse)
async def get_forecast(
    city: str = Query(..., min_length=2, max_length=100),
    days: int = Query(...),
) -> ForecastResponse:
    """Возвращает прогноз на 1/3/10 дней с min/max температурой."""
    try:
        query = ForecastQuery(city=city, days=days)
        client = build_open_meteo_client()
        lat, lon, resolved_city = await client.get_city_coordinates(query.city)
        normalized_points = await client.get_daily_forecast(lat=lat, lon=lon, days=query.days)
    except ValueError as exc:
        logger.warning(
            "GET /api/forecast: ошибка валидации days=%s city_len=%s detail=%s",
            days,
            len(city),
            exc,
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OpenMeteoError as exc:
        logger.warning(
            "GET /api/forecast: ошибка Open-Meteo days=%s city_len=%s detail=%s",
            days,
            len(city),
            exc,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "GET /api/forecast: непредвиденная ошибка days=%s city_len=%s",
            days,
            len(city),
        )
        raise HTTPException(status_code=500, detail="Unexpected server error") from exc

    logger.info(
        "GET /api/forecast: ok days=%s resolved_city=%s points=%s",
        query.days,
        resolved_city,
        len(normalized_points),
    )
    return ForecastResponse(
        city=resolved_city,
        days=query.days,
        forecast=normalized_points,
    )


# Раздаем Mini App по корневому пути, чтобы Telegram открывал готовую страницу.
if MINIAPP_DIR.exists():
    app.mount("/", StaticFiles(directory=MINIAPP_DIR, html=True), name="miniapp")
