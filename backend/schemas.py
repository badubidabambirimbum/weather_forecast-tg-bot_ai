"""Pydantic-схемы backend для API прогноза."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# События Mini App для POST /api/events (согласованы с miniapp/logger.js).
MiniappClientEvent = Literal[
    "miniapp_ready",
    "submit_forecast",
    "forecast_ok",
    "forecast_error",
    "command_hint_used",
]


class ForecastQuery(BaseModel):
    """Входные параметры запроса дневного прогноза."""

    city: str = Field(min_length=2, max_length=100)
    days: int

    @field_validator("days")
    @classmethod
    def validate_days(cls, value: int) -> int:
        """Ограничивает горизонт прогноза фиксированным набором для MVP."""
        if value not in (1, 3, 10):
            raise ValueError("days must be one of: 1, 3, 10")
        return value


class ForecastPoint(BaseModel):
    """Одна точка дневного прогноза."""

    date: str
    min_temp_c: float
    max_temp_c: float
    weather_code: int = Field(description="Код погоды WMO (Open-Meteo); для иконок на фронтенде.")
    weather: str


class ForecastResponse(BaseModel):
    """Ответ API для выдачи прогноза в Mini App."""

    city: str
    days: int
    forecast: list[ForecastPoint]


class GeocodeSuggestion(BaseModel):
    """Один вариант автодополнения города (Open-Meteo Geocoding)."""

    name: str = Field(description="Имя для запроса прогноза (как в геокодере).")
    label: str = Field(description="Подпись в списке: город, регион, страна.")


class GeocodeResponse(BaseModel):
    """Ответ подсказок по городам для поля ввода Mini App."""

    suggestions: list[GeocodeSuggestion]


class EventRequest(BaseModel):
    """Событие от Mini App для серверного лога.

    В payload допускаются обезличенные метрики и поля пользователя из Telegram WebApp
    (tg_user_id, tg_username, tg_first_name и т.д.), без init_data и токенов.
    """

    event: MiniappClientEvent
    payload: dict[str, str | int] = Field(default_factory=dict)
    client_ts_ms: int | None = Field(default=None, description="Время на клиенте (epoch ms), опционально.")

    @field_validator("payload")
    @classmethod
    def validate_payload_bounds(cls, value: dict[str, str | int]) -> dict[str, str | int]:
        """Ограничивает размер payload, чтобы публичный endpoint нельзя было забить мегабайтами."""
        if len(value) > 32:
            raise ValueError("payload: слишком много ключей (максимум 32)")
        cleaned: dict[str, str | int] = {}
        for key, raw in value.items():
            if len(key) > 64:
                raise ValueError("payload: ключ слишком длинный")
            if isinstance(raw, str):
                if len(raw) > 512:
                    raise ValueError("payload: строковое значение слишком длинное")
                cleaned[key] = raw
            elif isinstance(raw, bool):
                raise ValueError("payload: недопустимый тип (ожидаются str или int)")
            elif isinstance(raw, int):
                if abs(raw) > 2**31 - 1:
                    raise ValueError("payload: целое вне допустимого диапазона")
                cleaned[key] = raw
            else:
                raise ValueError("payload: недопустимый тип значения")
        return cleaned

