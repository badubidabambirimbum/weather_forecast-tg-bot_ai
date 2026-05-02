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
    assert response.status_code == 422


def test_geocode_endpoint_success(monkeypatch) -> None:
    """Проверяет выдачу подсказок городов через замоканный клиент Open-Meteo."""
    monkeypatch.setattr(app_module, "build_open_meteo_client", lambda: FakeOpenMeteoClient())
    client = TestClient(app_module.app)
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
    response = client.get("/api/geocode", params={"query": "пусто"})
    assert response.status_code == 200
    assert response.json()["suggestions"] == []


def test_geocode_query_too_short() -> None:
    """Слишком короткий query отклоняется валидацией FastAPI."""
    client = TestClient(app_module.app)
    response = client.get("/api/geocode", params={"query": "я"})
    assert response.status_code == 422
