"""Pydantic-схемы backend для API прогноза."""

from pydantic import BaseModel, Field, field_validator


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

