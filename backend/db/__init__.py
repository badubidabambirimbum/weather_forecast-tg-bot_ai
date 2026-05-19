"""Доступ к PostgreSQL: engine, ORM-модели, репозиторий."""

from backend.db.engine import (
    check_connection,
    dispose_engine,
    get_async_session,
    get_database_url,
    init_engine,
    is_engine_initialized,
)
from backend.db.models import Base, ForecastRequest, User
from backend.db.repository import (
    ForecastRequestStatus,
    UserProfile,
    record_forecast_request,
    record_forecast_request_safe,
    upsert_user,
    upsert_user_safe,
    user_profile_from_aiogram,
    user_profile_from_telegram,
)

__all__ = [
    "Base",
    "User",
    "ForecastRequest",
    "ForecastRequestStatus",
    "UserProfile",
    "check_connection",
    "dispose_engine",
    "get_async_session",
    "get_database_url",
    "init_engine",
    "is_engine_initialized",
    "record_forecast_request",
    "record_forecast_request_safe",
    "upsert_user",
    "upsert_user_safe",
    "user_profile_from_aiogram",
    "user_profile_from_telegram",
]
