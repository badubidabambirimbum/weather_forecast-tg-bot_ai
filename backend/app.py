from __future__ import annotations

import base64
import hashlib
import hmac
import json
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
    PublicConfigResponse,
    TelegramSessionRequest,
)
from backend.db.engine import check_connection, dispose_engine, init_engine, is_engine_initialized
from backend.db.repository import (
    record_forecast_request_safe,
    upsert_user_safe,
    user_profile_from_telegram,
)
from backend.services.open_meteo import OpenMeteoClient, OpenMeteoError
from backend.telegram_webapp import TelegramInitDataError, verify_init_data

load_dotenv()

logger = logging.getLogger(__name__)
events_logger = logging.getLogger("backend.events")

# Путь к статическим файлам Mini App (HTML/CSS/JS).
MINIAPP_DIR = Path(__file__).resolve().parent.parent / "miniapp"

# In-memory rate limit для POST /api/events: не более 60 запросов с одного IP за 60 с.
_event_rate_store: dict[str, list[float]] = {}
_EVENTS_WINDOW_SEC = 60.0
_EVENTS_MAX_PER_WINDOW = 60
_SESSION_COOKIE_NAME = "wf_session"
_SESSION_MAX_AGE_SEC = 86400
_SERVER_ERROR_PUBLIC = "Unexpected server error"


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


def _is_database_configured() -> bool:
    """True, если задан DATABASE_URL (PostgreSQL)."""
    return bool(os.getenv("DATABASE_URL", "").strip())


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Логирование, подключение к PostgreSQL (если настроено), остановка engine."""
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    for log_name in (
        "backend",
        "backend.app",
        "backend.services",
        "backend.services.open_meteo",
        "backend.events",
        "backend.db",
    ):
        logging.getLogger(log_name).setLevel(level)
    # Явный вывод в консоль для ключевых логгеров (иначе INFO «теряется» при запуске через uvicorn).
    _attach_stderr_handler("backend.app", level)
    _attach_stderr_handler("backend.events", level)
    if _is_database_configured():
        init_engine()
        if not await check_connection():
            raise RuntimeError("Не удалось подключиться к PostgreSQL (DATABASE_URL)")
        logger.info("PostgreSQL: подключение установлено")
    else:
        logger.warning("DATABASE_URL не задан — запись профиля и истории прогнозов отключена")
    logger.info("Backend запущен: LOG_LEVEL=%s", level_name)
    try:
        yield
    finally:
        if is_engine_initialized():
            await dispose_engine()
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


@app.middleware("http")
async def miniapp_static_no_store(request: Request, call_next):
    """Не кешировать HTML/CSS/JS Mini App — Telegram WebView часто держит старый index/app.js без bootstrap."""
    response = await call_next(request)
    if request.method != "GET":
        return response
    path = request.url.path
    if path.startswith("/api"):
        return response
    if path == "/" or path.endswith((".html", ".js", ".css")):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


@app.middleware("http")
async def miniapp_strip_conditional_request_headers(request: Request, call_next):
    """Снимает If-None-Match / If-Modified-Since для статики Mini App.

    Иначе Starlette StaticFiles отвечает 304, Telegram WebView остаётся на старом `app.js`
    (в логах нет `GET /app.js` / нет `POST /api/session`, сразу `POST /api/events` → 401).
    """
    if request.method != "GET":
        return await call_next(request)
    path = request.url.path
    if path.startswith("/api"):
        return await call_next(request)
    if path == "/" or path.endswith((".html", ".js", ".css")):
        headers = [
            (k, v)
            for k, v in request.scope.get("headers", [])
            if k.lower() not in (b"if-none-match", b"if-modified-since")
        ]
        new_scope = {**request.scope, "headers": headers}
        request = Request(new_scope)
    return await call_next(request)


def build_open_meteo_client() -> OpenMeteoClient:
    """Создает клиент Open-Meteo (без API-ключа)."""
    return OpenMeteoClient()


def _get_required_env(name: str) -> str:
    """Читает обязательную переменную окружения и валидирует её."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


def _get_session_secret() -> str:
    """Секрет подписи session cookie."""
    return _get_required_env("SESSION_SECRET")


def _get_bot_token() -> str:
    """Токен Telegram-бота для проверки initData."""
    return _get_required_env("BOT_TOKEN")


def _get_init_data_max_age_seconds() -> int:
    """Максимальный возраст initData в секундах."""
    raw = os.getenv("INIT_DATA_MAX_AGE_SEC", str(_SESSION_MAX_AGE_SEC)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("INIT_DATA_MAX_AGE_SEC must be an integer") from exc
    if value <= 0:
        raise RuntimeError("INIT_DATA_MAX_AGE_SEC must be positive")
    return value


def _get_cookie_secure_flag() -> bool:
    """Нужно ли ставить Secure для session cookie."""
    return os.getenv("COOKIE_SECURE", "0").strip().lower() in {"1", "true", "yes", "on"}


def _get_cookie_samesite() -> str:
    """Политика SameSite для session cookie."""
    raw = os.getenv("COOKIE_SAMESITE", "lax").strip().lower()
    if raw in {"lax", "strict", "none"}:
        return raw
    raise RuntimeError("COOKIE_SAMESITE must be one of: lax, strict, none")


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    pad_len = (4 - len(raw) % 4) % 4
    return base64.urlsafe_b64decode(raw + ("=" * pad_len))


def _sign_session_payload(payload_b64: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()


def _build_session_token(*, user_id: int, auth_date: int, username: str | None) -> str:
    """Создаёт подписанный токен для HttpOnly cookie."""
    now = int(time.time())
    exp = now + _SESSION_MAX_AGE_SEC
    payload_obj = {"uid": user_id, "auth_date": auth_date, "exp": exp}
    if username:
        payload_obj["username"] = username
    payload_json = json.dumps(payload_obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    payload_b64 = _b64url_encode(payload_json)
    signature = _sign_session_payload(payload_b64, _get_session_secret())
    return f"{payload_b64}.{signature}"


def _verify_session_token(token: str) -> dict[str, int | str]:
    """Проверяет подпись и срок действия session cookie."""
    try:
        payload_b64, sig = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Unauthorized") from exc
    expected_sig = _sign_session_payload(payload_b64, _get_session_secret())
    if not hmac.compare_digest(sig, expected_sig):
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        payload_raw = _b64url_decode(payload_b64)
        payload = json.loads(payload_raw.decode("utf-8"))
    except Exception as exc:  # pragma: no cover - защитный путь для битого токена
        raise HTTPException(status_code=401, detail="Unauthorized") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=401, detail="Unauthorized")

    uid = payload.get("uid")
    exp = payload.get("exp")
    auth_date = payload.get("auth_date")
    if not isinstance(uid, int) or isinstance(uid, bool):
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not isinstance(exp, int) or not isinstance(auth_date, int):
        raise HTTPException(status_code=401, detail="Unauthorized")
    if exp < int(time.time()):
        raise HTTPException(status_code=401, detail="Unauthorized")

    out: dict[str, int | str] = {"uid": uid, "exp": exp, "auth_date": auth_date}
    username = payload.get("username")
    if isinstance(username, str):
        out["username"] = username
    return out


def _require_telegram_session(request: Request) -> dict[str, int | str]:
    """Извлекает и проверяет user-контекст из session cookie."""
    token = request.cookies.get(_SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return _verify_session_token(token)


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
    session: Annotated[dict[str, int | str], Depends(_require_telegram_session)],
    _rate: Annotated[None, Depends(_enforce_events_rate_limit)],
    body: EventRequest,
) -> Response:
    """Принимает события аналитики из Mini App; пишет в лог, без хранения PII в ответе."""
    events_logger.info(
        "event=%s tg_user_id=%s payload=%s client_ts_ms=%s",
        body.event,
        session["uid"],
        body.payload,
        body.client_ts_ms,
    )
    return Response(status_code=204)


@app.get("/health")
async def healthcheck() -> dict[str, bool]:
    """Проверка, что backend запущен; при настроенной БД — также db."""
    result: dict[str, bool] = {"ok": True}
    if is_engine_initialized():
        result["db"] = await check_connection()
    return result


@app.get("/api/public/config", response_model=PublicConfigResponse)
async def public_config() -> PublicConfigResponse:
    """Публичная конфигурация для Mini App (ссылка на бота для экрана «только Telegram»)."""
    raw = os.getenv("BOT_URL", "").strip()
    return PublicConfigResponse(bot_url=raw or None)


@app.post("/api/session", status_code=204)
async def create_telegram_session(
    body: TelegramSessionRequest,
    request: Request,
    response: Response,
) -> Response:
    """Проверяет initData и выставляет подписанную HttpOnly session cookie."""
    try:
        verified = verify_init_data(
            body.init_data,
            bot_token=_get_bot_token(),
            max_age_seconds=_get_init_data_max_age_seconds(),
        )
    except TelegramInitDataError as exc:
        raise HTTPException(status_code=401, detail="Invalid Telegram init data") from exc
    except RuntimeError as exc:
        logger.error("Ошибка конфигурации /api/session: %s", exc)
        raise HTTPException(status_code=500, detail="Server auth config error") from exc

    if verified.user is None:
        raise HTTPException(status_code=401, detail="Telegram user is missing")

    await upsert_user_safe(user_profile_from_telegram(verified.user), source="miniapp")

    token = _build_session_token(
        user_id=verified.user.id,
        auth_date=verified.auth_date,
        username=verified.user.username,
    )
    cookie_samesite = _get_cookie_samesite()
    cookie_secure = _get_cookie_secure_flag()
    if cookie_samesite == "none" and not cookie_secure:
        # Современные браузеры отвергнут SameSite=None без Secure.
        cookie_secure = True
    response.set_cookie(
        key=_SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,
        max_age=_SESSION_MAX_AGE_SEC,
        path="/",
    )
    response.status_code = 204
    return response


@app.get("/api/geocode", response_model=GeocodeResponse)
async def geocode_suggest(
    _session: Annotated[dict[str, int | str], Depends(_require_telegram_session)],
    query: str = Query(..., min_length=2, max_length=80),
) -> GeocodeResponse:
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
    session: Annotated[dict[str, int | str], Depends(_require_telegram_session)],
    city: str = Query(..., min_length=2, max_length=100),
    days: int = Query(...),
) -> ForecastResponse:
    """Возвращает прогноз на 1/3/10 дней с min/max температурой."""
    telegram_user_id = int(session["uid"])
    resolved_city: str | None = None
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
        await record_forecast_request_safe(
            telegram_user_id=telegram_user_id,
            source="miniapp",
            query_city=city,
            days=days,
            status="validation_error",
            http_status=422,
            error_detail=str(exc),
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OpenMeteoError as exc:
        logger.warning(
            "GET /api/forecast: ошибка Open-Meteo days=%s city_len=%s detail=%s",
            days,
            len(city),
            exc,
        )
        await record_forecast_request_safe(
            telegram_user_id=telegram_user_id,
            source="miniapp",
            query_city=city,
            days=days,
            status="open_meteo_error",
            resolved_city=resolved_city,
            http_status=400,
            error_detail=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "GET /api/forecast: непредвиденная ошибка days=%s city_len=%s",
            days,
            len(city),
        )
        await record_forecast_request_safe(
            telegram_user_id=telegram_user_id,
            source="miniapp",
            query_city=city,
            days=days,
            status="server_error",
            resolved_city=resolved_city,
            http_status=500,
            error_detail=_SERVER_ERROR_PUBLIC,
        )
        raise HTTPException(status_code=500, detail=_SERVER_ERROR_PUBLIC) from exc

    await record_forecast_request_safe(
        telegram_user_id=telegram_user_id,
        source="miniapp",
        query_city=city,
        days=query.days,
        status="success",
        resolved_city=resolved_city,
        http_status=200,
    )
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
