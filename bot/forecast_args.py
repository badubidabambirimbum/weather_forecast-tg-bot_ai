"""Парсинг аргументов /forecast и форматирование ответа (импорт без токена — удобно для тестов)."""

from __future__ import annotations


def parse_forecast_args(args: str | None) -> tuple[str, int] | None:
    """Разбирает строку после `/forecast`: город и опционально дни 1/3/10 (по умолчанию 3).

    Последний токен, если это «1», «3» или «10», считается горизонтом; остальное — название города
    (чтобы поддерживать города из нескольких слов).

    Возвращает ``(city, days)`` или ``None``, если города нет или он слишком короткий.
    """
    if not args or not str(args).strip():
        return None
    parts = str(args).strip().split()
    if not parts:
        return None
    if len(parts) >= 2 and parts[-1] in ("1", "3", "10"):
        days = int(parts[-1])
        city = " ".join(parts[:-1]).strip()
    else:
        city = " ".join(parts).strip()
        days = 3
    if len(city) < 2:
        return None
    if len(city) > 100:
        city = city[:100]
    return city, days


def format_forecast_text(resolved_city: str, days: int, points: list[dict]) -> str:
    """Собирает многострочный текст прогноза для чата Telegram (до ~3500 символов с запасом)."""
    lines = [f"Прогноз: {resolved_city}, {days} дн.", "Источник: Open‑Meteo.", ""]
    for p in points:
        date = p.get("date", "")
        w = p.get("weather", "")
        mn = p.get("min_temp_c")
        mx = p.get("max_temp_c")
        lines.append(f"{date}: min {mn} … max {mx}, {w}")
    text = "\n".join(lines)
    if len(text) > 3800:
        text = text[:3797] + "…"
    return text
