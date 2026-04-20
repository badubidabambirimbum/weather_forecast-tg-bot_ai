import os

from dotenv import load_dotenv

load_dotenv()


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")

# Для локальной отладки Mini App без Telegram (опционально)
ALLOW_UNVERIFIED_MINI_APP = os.getenv("ALLOW_UNVERIFIED_MINI_APP", "0").strip() in (
    "1",
    "true",
    "yes",
)
