from __future__ import annotations

import httpx

FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"


async def fetch_forecast(api_key: str, city: str) -> dict:
    """Прогноз на 5 дней (шаг 3 ч), ответ на русском, метрические единицы."""
    params = {
        "q": city,
        "appid": api_key,
        "units": "metric",
        "lang": "ru",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(FORECAST_URL, params=params)
    if r.status_code == 404:
        raise ValueError("Город не найден. Проверьте название.")
    r.raise_for_status()
    data = r.json()

    city_name = data.get("city", {}).get("name", city)
    country = data.get("city", {}).get("country", "")
    location = f"{city_name}, {country}".strip(", ")

    # Группируем по дате (локальное время из API — UTC offset в city)
    from collections import defaultdict
    from datetime import datetime, timedelta, timezone

    tz = int(data.get("city", {}).get("timezone", 0) or 0)
    by_day: dict[str, list] = defaultdict(list)
    for item in data.get("list", []):
        ts = item.get("dt", 0)
        if not ts:
            continue
        utc = datetime.fromtimestamp(ts, tz=timezone.utc)
        local = utc + timedelta(seconds=tz)
        day_key = local.strftime("%Y-%m-%d")
        by_day[day_key].append(item)

    daily_summaries = []
    for day_key in sorted(by_day.keys())[:5]:
        slots = by_day[day_key]
        temps = [s["main"]["temp"] for s in slots if "main" in s]
        feels = [s["main"]["feels_like"] for s in slots if "main" in s]
        descriptions = [s["weather"][0]["description"] for s in slots if s.get("weather")]
        wind = max((s.get("wind", {}).get("speed") or 0) for s in slots)
        humidity = sum(s["main"]["humidity"] for s in slots if "main" in s) / max(
            len([s for s in slots if "main" in s]), 1
        )
        pop = max((s.get("pop", 0) or 0) for s in slots)
        label = datetime.strptime(day_key, "%Y-%m-%d").strftime("%d.%m")
        daily_summaries.append(
            {
                "date": day_key,
                "label": label,
                "temp_min": round(min(temps), 1) if temps else None,
                "temp_max": round(max(temps), 1) if temps else None,
                "feels_like_min": round(min(feels), 1) if feels else None,
                "feels_like_max": round(max(feels), 1) if feels else None,
                "description": _most_common(descriptions) if descriptions else "",
                "wind_max_ms": round(wind, 1),
                "humidity_avg": round(humidity, 0),
                "precipitation_prob_max": round(pop * 100),
                "slots": len(slots),
            }
        )

    # Ближайшие интервалы для детализации «сейчас / сегодня»
    now_slots = data.get("list", [])[:8]

    return {
        "location": location,
        "daily": daily_summaries,
        "near_term": [
            {
                "time_utc": x.get("dt"),
                "temp": x.get("main", {}).get("temp"),
                "feels_like": x.get("main", {}).get("feels_like"),
                "description": (x.get("weather") or [{}])[0].get("description", ""),
                "wind_ms": x.get("wind", {}).get("speed"),
                "pop_percent": round((x.get("pop") or 0) * 100),
            }
            for x in now_slots
        ],
    }


def _most_common(items: list[str]) -> str:
    if not items:
        return ""
    counts: dict[str, int] = {}
    for i in items:
        counts[i] = counts.get(i, 0) + 1
    return max(counts, key=counts.get)
