from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Единый ответ для этапа проверки интеграции Mini App.
MOCK_MESSAGE = "Здесь скоро появится прогноз погоды, следите за новостями:)"

# Путь к статическим файлам Mini App (HTML/CSS/JS).
MINIAPP_DIR = Path(__file__).resolve().parent.parent / "miniapp"

# Инициализация backend приложения.
app = FastAPI(
    title="Weather Mini App Backend",
    description="Каркас backend для шага 1: проверка интеграции Telegram Mini App.",
    version="0.1.0",
)


@app.get("/health")
async def healthcheck() -> dict[str, bool]:
    """Проверка, что backend запущен и отвечает."""
    return {"ok": True}


@app.get("/api/mock")
async def mock_message() -> JSONResponse:
    """Тестовый endpoint для кнопки в Mini App на шаге 1."""
    return JSONResponse(content={"message": MOCK_MESSAGE})


# Раздаем Mini App по корневому пути, чтобы Telegram открывал готовую страницу.
if MINIAPP_DIR.exists():
    app.mount("/", StaticFiles(directory=MINIAPP_DIR, html=True), name="miniapp")
