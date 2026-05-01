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
    weather: str


class ForecastResponse(BaseModel):
    """Ответ API для выдачи прогноза в Mini App."""

    city: str
    days: int
    forecast: list[ForecastPoint]

