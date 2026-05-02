"""Клиент Open-Meteo для геокодинга и дневного прогноза."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


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
        logger.debug(
            "Open-Meteo geocoding: query_len=%s",
            len(city),
        )
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(self.geo_url, params=params)
        except httpx.RequestError:
            logger.exception("Open-Meteo geocoding: сетевая ошибка запроса")
            raise OpenMeteoError("Geo API request failed") from None

        if response.status_code != 200:
            logger.warning(
                "Open-Meteo geocoding: неуспешный HTTP status=%s",
                response.status_code,
            )
            raise OpenMeteoError("Geo API request failed")

        payload = response.json()
        results = payload.get("results", [])
        if not results:
            logger.info("Open-Meteo geocoding: город не найден (пустой results)")
            raise OpenMeteoError("City not found")

        first = results[0]
        return float(first["latitude"]), float(first["longitude"]), first.get("name", city)

    async def suggest_cities(self, query: str, limit: int = 8) -> list[dict[str, str]]:
        """Возвращает до `limit` подсказок городов по префиксу/фрагменту имени (пустой список, если ничего не найдено)."""
        trimmed = query.strip()
        if len(trimmed) < 2:
            return []
        limit = max(1, min(int(limit), 10))
        params = {"name": trimmed, "count": limit, "language": "ru", "format": "json"}
        logger.debug("Open-Meteo geocoding suggest: query_len=%s limit=%s", len(trimmed), limit)
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(self.geo_url, params=params)
        except httpx.RequestError:
            logger.exception("Open-Meteo geocoding suggest: сетевая ошибка запроса")
            raise OpenMeteoError("Geo API request failed") from None

        if response.status_code != 200:
            logger.warning(
                "Open-Meteo geocoding suggest: неуспешный HTTP status=%s",
                response.status_code,
            )
            raise OpenMeteoError("Geo API request failed")

        payload = response.json()
        results = payload.get("results") or []
        out: list[dict[str, str]] = []
        for r in results:
            name = str(r.get("name", "")).strip()
            if not name:
                continue
            raw_country = r.get("country")
            country = str(raw_country).strip() if raw_country is not None else ""
            raw_admin1 = r.get("admin1")
            admin1 = str(raw_admin1).strip() if raw_admin1 is not None else ""
            parts: list[str] = [name]
            if admin1 and admin1.casefold() != name.casefold():
                parts.append(admin1)
            if country:
                parts.append(country)
            label = ", ".join(parts)
            out.append({"name": name, "label": label})
        return out

    async def get_daily_forecast(self, lat: float, lon: float, days: int) -> list[dict]:
        """Возвращает список дневного прогноза за выбранное число дней."""
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,weather_code",
            "timezone": "UTC",
            "forecast_days": days,
        }
        logger.debug(
            "Open-Meteo forecast: days=%s lat=%.4f lon=%.4f",
            days,
            lat,
            lon,
        )
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(self.forecast_url, params=params)
        except httpx.RequestError:
            logger.exception("Open-Meteo forecast: сетевая ошибка запроса")
            raise OpenMeteoError("Forecast API request failed") from None

        if response.status_code != 200:
            logger.warning(
                "Open-Meteo forecast: неуспешный HTTP status=%s",
                response.status_code,
            )
            raise OpenMeteoError("Forecast API request failed")

        payload = response.json()
        daily = payload.get("daily", {})
        dates = daily.get("time", [])
        t_mins = daily.get("temperature_2m_min", [])
        t_maxs = daily.get("temperature_2m_max", [])
        w_codes = daily.get("weather_code", [])
        if not dates:
            logger.warning("Open-Meteo forecast: пустой блок daily.time")
            raise OpenMeteoError("Empty forecast response")

        points: list[dict] = []
        for date, t_min, t_max, code in zip(dates, t_mins, t_maxs, w_codes):
            try:
                code_int = int(code)
            except (TypeError, ValueError):
                code_int = 0
            points.append(
                {
                    "date": date,
                    "min_temp_c": round(float(t_min), 1),
                    "max_temp_c": round(float(t_max), 1),
                    "weather_code": code_int,
                    "weather": WEATHER_CODE_RU.get(code_int, "нет данных"),
                }
            )
        return points
