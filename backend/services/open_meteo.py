"""Клиент Open-Meteo для геокодинга и дневного прогноза."""

from __future__ import annotations

import httpx


class OpenMeteoError(Exception):
    """Доменно-ориентированная ошибка Open-Meteo."""


WEATHER_CODE_RU: dict[int, str] = {
    0: "ясно",
    1: "преимущественно ясно",
    2: "переменная облачность",
    3: "пасмурно",
    45: "туман",
    48: "изморозь",
    51: "слабая морось",
    53: "морось",
    55: "сильная морось",
    61: "слабый дождь",
    63: "дождь",
    65: "сильный дождь",
    71: "слабый снег",
    73: "снег",
    75: "сильный снег",
    80: "ливень",
    81: "ливень",
    82: "сильный ливень",
    95: "гроза",
    96: "гроза с градом",
    99: "сильная гроза с градом",
}


class OpenMeteoClient:
    """Обертка Open-Meteo API с возвратом данных в формате проекта."""

    def __init__(self, timeout_seconds: float = 15.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.geo_url = "https://geocoding-api.open-meteo.com/v1/search"
        self.forecast_url = "https://api.open-meteo.com/v1/forecast"

    async def get_city_coordinates(self, city: str) -> tuple[float, float, str]:
        """Ищет координаты города через Open-Meteo geocoding API."""
        params = {"name": city, "count": 1, "language": "ru", "format": "json"}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(self.geo_url, params=params)
        if response.status_code != 200:
            raise OpenMeteoError("Geo API request failed")

        payload = response.json()
        results = payload.get("results", [])
        if not results:
            raise OpenMeteoError("City not found")

        first = results[0]
        return float(first["latitude"]), float(first["longitude"]), first.get("name", city)

    async def get_daily_forecast(self, lat: float, lon: float, days: int) -> list[dict]:
        """Возвращает список дневного прогноза за выбранное число дней."""
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,weather_code",
            "timezone": "UTC",
            "forecast_days": days,
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(self.forecast_url, params=params)
        if response.status_code != 200:
            raise OpenMeteoError("Forecast API request failed")

        payload = response.json()
        daily = payload.get("daily", {})
        dates = daily.get("time", [])
        t_mins = daily.get("temperature_2m_min", [])
        t_maxs = daily.get("temperature_2m_max", [])
        w_codes = daily.get("weather_code", [])
        if not dates:
            raise OpenMeteoError("Empty forecast response")

        points: list[dict] = []
        for date, t_min, t_max, code in zip(dates, t_mins, t_maxs, w_codes):
            points.append(
                {
                    "date": date,
                    "min_temp_c": round(float(t_min), 1),
                    "max_temp_c": round(float(t_max), 1),
                    "weather": WEATHER_CODE_RU.get(int(code), "нет данных"),
                }
            )
        return points
