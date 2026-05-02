"""Тесты парсинга /forecast без запуска бота и без BOT_TOKEN."""

from bot.forecast_args import format_forecast_text, parse_forecast_args


def test_parse_forecast_city_only_defaults_days() -> None:
    out = parse_forecast_args("Москва")
    assert out is not None
    city, days = out
    assert city == "Москва"
    assert days == 3


def test_parse_forecast_city_and_days() -> None:
    out = parse_forecast_args("Санкт-Петербург 10")
    assert out is not None
    assert out[0] == "Санкт-Петербург"
    assert out[1] == 10


def test_parse_forecast_last_token_days_multiword_city() -> None:
    out = parse_forecast_args("Нью Йорк 1")
    assert out is not None
    assert out[0] == "Нью Йорк"
    assert out[1] == 1


def test_parse_forecast_empty() -> None:
    assert parse_forecast_args(None) is None
    assert parse_forecast_args("") is None
    assert parse_forecast_args("   ") is None


def test_parse_forecast_city_too_short() -> None:
    assert parse_forecast_args("я") is None


def test_format_forecast_text() -> None:
    text = format_forecast_text(
        "Москва",
        1,
        [{"date": "2024-01-01", "min_temp_c": 1.0, "max_temp_c": 2.0, "weather": "ясно"}],
    )
    assert "Москва" in text
    assert "2024-01-01" in text
    assert "ясно" in text
