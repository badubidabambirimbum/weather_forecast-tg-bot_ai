import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from fastapi.testclient import TestClient

import backend.app as app_module


class FakeOpenMeteoClient:
    """Тестовый клиент Open-Meteo для изоляции endpoint логики от внешнего API."""

    async def get_city_coordinates(self, city: str) -> tuple[float, float, str]:
        return 55.75, 37.62, "Москва"

    async def get_daily_forecast(self, lat: float, lon: float, days: int) -> list[dict]:
        return [
            {
                "date": "2024-04-25",
                "min_temp_c": 5.2,
                "max_temp_c": 12.7,
                "weather_code": 61,
                "weather": "небольшой дождь",
            }
            for _ in range(days)
        ]

    async def suggest_cities(self, query: str, limit: int = 8) -> list[dict[str, str]]:
        if "пусто" in query.casefold():
            return []
        return [
            {"name": "Москва", "label": "Москва, Москва, Россия"},
            {"name": "Москва", "label": "Москва, США"},
        ][:limit]


def _make_init_data(fields: dict[str, str], bot_token: str) -> str:
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    payload = dict(fields)
    payload["hash"] = calc_hash
    return urlencode(payload)


def _auth_client(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123456:TEST_BOT_TOKEN")
    monkeypatch.setenv("SESSION_SECRET", "test_session_secret")
    monkeypatch.setenv("INIT_DATA_MAX_AGE_SEC", "86400")
    # Изоляция от локального .env: Secure-cookie не сохраняется у TestClient по HTTP.
    monkeypatch.setenv("COOKIE_SAMESITE", "lax")
    monkeypatch.setenv("COOKIE_SECURE", "0")
    now = int(time.time())
    fields = {
        "auth_date": str(now),
        "query_id": "AAEAAAE",
        "user": json.dumps({"id": 123456789, "username": "alexey"}, separators=(",", ":")),
    }
    init_data = _make_init_data(fields, "123456:TEST_BOT_TOKEN")
    response = client.post("/api/session", json={"init_data": init_data})
    assert response.status_code == 204


def test_health_endpoint() -> None:
    """Проверяет healthcheck endpoint для smoke-тестов деплоя."""
    client = TestClient(app_module.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_forecast_endpoint_success(monkeypatch) -> None:
    """Проверяет успешную выдачу прогноза при валидных параметрах."""
    monkeypatch.setattr(app_module, "build_open_meteo_client", lambda: FakeOpenMeteoClient())
    client = TestClient(app_module.app)
    _auth_client(client, monkeypatch)
    response = client.get("/api/forecast", params={"city": "Moscow", "days": 3})

    assert response.status_code == 200
    payload = response.json()
    assert payload["city"] == "Москва"
    assert payload["days"] == 3
    assert len(payload["forecast"]) == 3
    assert payload["forecast"][0]["min_temp_c"] == 5.2
    assert payload["forecast"][0]["max_temp_c"] == 12.7
    assert payload["forecast"][0]["weather_code"] == 61


def test_forecast_endpoint_validation_error() -> None:
    """Проверяет валидацию days: должны приниматься только 1/3/10."""
    client = TestClient(app_module.app)
    response = client.get("/api/forecast", params={"city": "Moscow", "days": 2})
    assert response.status_code == 401


def test_geocode_endpoint_success(monkeypatch) -> None:
    """Проверяет выдачу подсказок городов через замоканный клиент Open-Meteo."""
    monkeypatch.setattr(app_module, "build_open_meteo_client", lambda: FakeOpenMeteoClient())
    client = TestClient(app_module.app)
    _auth_client(client, monkeypatch)
    response = client.get("/api/geocode", params={"query": "Мос"})

    assert response.status_code == 200
    payload = response.json()
    assert "suggestions" in payload
    assert len(payload["suggestions"]) == 2
    assert payload["suggestions"][0]["name"] == "Москва"
    assert "Россия" in payload["suggestions"][0]["label"]


def test_geocode_endpoint_empty(monkeypatch) -> None:
    """Пустой список подсказок при отсутствии совпадений (не ошибка)."""
    monkeypatch.setattr(app_module, "build_open_meteo_client", lambda: FakeOpenMeteoClient())
    client = TestClient(app_module.app)
    _auth_client(client, monkeypatch)
    response = client.get("/api/geocode", params={"query": "пусто"})
    assert response.status_code == 200
    assert response.json()["suggestions"] == []


def test_geocode_query_too_short() -> None:
    """Слишком короткий query отклоняется валидацией FastAPI."""
    client = TestClient(app_module.app)
    response = client.get("/api/geocode", params={"query": "я"})
    assert response.status_code == 401


def test_events_endpoint_accepts_known_event(monkeypatch) -> None:
    """POST /api/events принимает известное событие и отвечает 204."""
    app_module._event_rate_store.clear()
    client = TestClient(app_module.app)
    _auth_client(client, monkeypatch)
    response = client.post(
        "/api/events",
        json={
            "event": "miniapp_ready",
            "payload": {"has_tg": 1},
            "client_ts_ms": 1700000000000,
        },
    )
    assert response.status_code == 204
    assert response.content == b""


def test_events_endpoint_rejects_unknown_event(monkeypatch) -> None:
    """Неизвестное имя события отклоняется валидацией."""
    client = TestClient(app_module.app)
    _auth_client(client, monkeypatch)
    response = client.post("/api/events", json={"event": "not_a_real_event", "payload": {}})
    assert response.status_code == 422


def test_events_endpoint_rate_limit_429(monkeypatch) -> None:
    """С 61-го запроса за минуту с того же IP — 429."""
    app_module._event_rate_store.clear()
    client = TestClient(app_module.app)
    _auth_client(client, monkeypatch)
    body = {"event": "miniapp_ready", "payload": {}}
    for _ in range(60):
        assert client.post("/api/events", json=body).status_code == 204
    assert client.post("/api/events", json=body).status_code == 429
    app_module._event_rate_store.clear()


def test_session_endpoint_rejects_invalid_init_data(monkeypatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123456:TEST_BOT_TOKEN")
    monkeypatch.setenv("SESSION_SECRET", "test_session_secret")
    client = TestClient(app_module.app)
    response = client.post("/api/session", json={"init_data": "hash=deadbeef"})
    assert response.status_code == 401


def test_forecast_requires_session_cookie() -> None:
    client = TestClient(app_module.app)
    response = client.get("/api/forecast", params={"city": "Moscow", "days": 3})
    assert response.status_code == 401


def test_public_config_endpoint(monkeypatch) -> None:
    """GET /api/public/config доступен без сессии."""
    monkeypatch.setenv("BOT_URL", "https://t.me/test_weather_bot")
    client = TestClient(app_module.app)
    response = client.get("/api/public/config")
    assert response.status_code == 200
    assert response.json() == {"bot_url": "https://t.me/test_weather_bot"}
