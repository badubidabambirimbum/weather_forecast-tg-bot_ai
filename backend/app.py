from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import Response

from backend.schemas import (
    EventRequest,
    ForecastQuery,
    ForecastResponse,
    GeocodeResponse,
    GeocodeSuggestion,
)
from backend.services.open_meteo import OpenMeteoClient, OpenMeteoError

load_dotenv()

logger = logging.getLogger(__name__)
events_logger = logging.getLogger("backend.events")

# Путь к статическим файлам Mini App (HTML/CSS/JS).
MINIAPP_DIR = Path(__file__).resolve().parent.parent / "miniapp"

# In-memory rate limit для POST /api/events: не более 60 запросов с одного IP за 60 с.
_event_rate_store: dict[str, list[float]] = {}
_EVENTS_WINDOW_SEC = 60.0
_EVENTS_MAX_PER_WINDOW = 60


def _attach_stderr_handler(log_name: str, level: int) -> None:
    """Вешает один StreamHandler на stderr, чтобы INFO из приложения были видны в консоли uvicorn.

    Без handler дочерние логгеры только propagate на root; при дефолтной конфигурации Python
    сообщения INFO часто не попадают в вывод (lastResort только WARNING+).
    """
    lg = logging.getLogger(log_name)
    if lg.handlers:
        return
    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    lg.addHandler(handler)
    lg.propagate = False


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Настройка логирования пакета backend при старте приложения (uvicorn)."""
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    for log_name in (
        "backend",
        "backend.app",
        "backend.services",
        "backend.services.open_meteo",
        "backend.events",
    ):
        logging.getLogger(log_name).setLevel(level)
    # Явный вывод в консоль для ключевых логгеров (иначе INFO «теряется» при запуске через uvicorn).
    _attach_stderr_handler("backend.app", level)
    _attach_stderr_handler("backend.events", level)
    logger.info("Backend запущен: LOG_LEVEL=%s", level_name)
    yield
    logger.info("Backend останавливается")


# Инициализация backend приложения.
# Здесь создаётся экземпляр FastAPI, задаются основные метаданные API и подключается кастомная "жизненная" функция lifespan,
# которая управляет настройкой логирования и сообщает о старте/остановке backend (см. функцию lifespan выше).
# Эту переменную app используют для подключения роутов и middleware ниже, а также при запуске через Uvicorn.
app = FastAPI(
    title="Weather Mini App Backend",
    description=(
        "Backend-сервис для Weather Mini App. "
        "Обеспечивает обработку событий, выдачу погодных данных и интеграцию с Telegram Mini App. "
        "Поддерживает тестирование интеграции, валидацию запросов, лимитирование событий и доступ к статическим файлам фронтенда."
    ),
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


def _client_ip_for_events(request: Request) -> str:
    """IP для rate limit; при X-Forwarded-For берётся первый hop (как у типичного прокси)."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()[:100] or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _enforce_events_rate_limit(request: Request) -> None:
    """Превышает лимит — HTTP 429. Не логирует тело и заголовки, кроме косвенного срабатывания лимита."""
    ip = _client_ip_for_events(request)
    now = time.monotonic()
    bucket = _event_rate_store.setdefault(ip, [])
    cutoff = now - _EVENTS_WINDOW_SEC
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)
    if len(bucket) >= _EVENTS_MAX_PER_WINDOW:
        raise HTTPException(status_code=429, detail="Too many events")
    bucket.append(now)


@app.post("/api/events", status_code=204)
async def post_client_event(
    _rate: Annotated[None, Depends(_enforce_events_rate_limit)],
    body: EventRequest,
) -> Response:
    """Принимает события аналитики из Mini App; пишет в лог, без хранения PII в ответе."""
    tg_uid = body.payload.get("tg_user_id")
    events_logger.info(
        "event=%s tg_user_id=%s payload=%s client_ts_ms=%s",
        body.event,
        tg_uid,
        body.payload,
        body.client_ts_ms,
    )
    return Response(status_code=204)


@app.get("/health")
async def healthcheck() -> dict[str, bool]:
    """Проверка, что backend запущен и отвечает."""
    return {"ok": True}


@app.get("/api/geocode", response_model=GeocodeResponse)
async def geocode_suggest(query: str = Query(..., min_length=2, max_length=80)) -> GeocodeResponse:
    """Подсказки городов для автодополнения (Open-Meteo Geocoding, без API-ключа)."""
    try:
        client = build_open_meteo_client()
        raw = await client.suggest_cities(query=query, limit=8)
    except OpenMeteoError as exc:
        logger.warning(
            "GET /api/geocode: ошибка Open-Meteo query_len=%s detail=%s",
            len(query),
            exc,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception:
        logger.exception("GET /api/geocode: непредвиденная ошибка query_len=%s", len(query))
        raise HTTPException(status_code=500, detail="Unexpected server error") from None

    suggestions = [GeocodeSuggestion(name=item["name"], label=item["label"]) for item in raw]
    logger.info("GET /api/geocode: ok query_len=%s count=%s", len(query), len(suggestions))
    return GeocodeResponse(suggestions=suggestions)


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
