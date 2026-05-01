from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.schemas import ForecastQuery, ForecastResponse
from backend.services.open_meteo import OpenMeteoClient, OpenMeteoError

# Единый ответ для этапа проверки интеграции Mini App.
MOCK_MESSAGE = "Здесь скоро появится прогноз погоды, следите за новостями:)"
load_dotenv()

# Путь к статическим файлам Mini App (HTML/CSS/JS).
MINIAPP_DIR = Path(__file__).resolve().parent.parent / "miniapp"

# Инициализация backend приложения.
app = FastAPI(
    title="Weather Mini App Backend",
    description="Каркас backend для шага 1: проверка интеграции Telegram Mini App.",
    version="0.1.0",
)


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
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OpenMeteoError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unexpected server error") from exc

    return ForecastResponse(
        city=resolved_city,
        days=query.days,
        forecast=normalized_points,
    )


# Раздаем Mini App по корневому пути, чтобы Telegram открывал готовую страницу.
if MINIAPP_DIR.exists():
    app.mount("/", StaticFiles(directory=MINIAPP_DIR, html=True), name="miniapp")
