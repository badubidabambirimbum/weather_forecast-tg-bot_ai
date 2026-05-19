"""Запись профиля пользователя и попыток прогноза в PostgreSQL."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.db.engine import _engine, get_async_session, is_engine_initialized
from backend.db.models import ForecastRequest, User
from backend.telegram_webapp import TelegramUser

logger = logging.getLogger(__name__)

UserSource = Literal["miniapp", "bot"]
ForecastRequestStatus = Literal[
    "success",
    "validation_error",
    "open_meteo_error",
    "server_error",
]

_MAX_ERROR_DETAIL_LEN = 512


@dataclass(frozen=True)
class UserProfile:
    """Нормализованный профиль для upsert (Mini App или бот)."""

    telegram_user_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None
    is_premium: bool | None = None


def user_profile_from_telegram(user: TelegramUser) -> UserProfile:
    """Собирает UserProfile из проверенного initData.user."""
    return UserProfile(
        telegram_user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
        is_premium=user.is_premium,
    )


def user_profile_from_aiogram(user: Any) -> UserProfile:
    """Собирает UserProfile из aiogram types.User (duck typing, без импорта aiogram)."""
    user_id = getattr(user, "id", None)
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        raise ValueError("aiogram user.id must be int")

    def _opt_str(attr: str) -> str | None:
        val = getattr(user, attr, None)
        if val is None:
            return None
        if not isinstance(val, str):
            return None
        stripped = val.strip()
        return stripped or None

    is_premium = getattr(user, "is_premium", None)
    if is_premium is not None and not isinstance(is_premium, bool):
        is_premium = None

    return UserProfile(
        telegram_user_id=user_id,
        username=_opt_str("username"),
        first_name=_opt_str("first_name"),
        last_name=_opt_str("last_name"),
        language_code=_opt_str("language_code"),
        is_premium=is_premium,
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _user_insert():
    """INSERT для upsert: SQLite в тестах, PostgreSQL в production."""
    if is_engine_initialized() and _engine is not None and _engine.dialect.name == "sqlite":
        return sqlite_insert(User)
    return pg_insert(User)


def _truncate_error_detail(detail: str | None) -> str | None:
    if detail is None:
        return None
    trimmed = detail.strip()
    if not trimmed:
        return None
    if len(trimmed) <= _MAX_ERROR_DETAIL_LEN:
        return trimmed
    return trimmed[:_MAX_ERROR_DETAIL_LEN]


async def upsert_user(profile: UserProfile, *, source: UserSource) -> None:
    """Создаёт или обновляет строку users (ON CONFLICT DO UPDATE)."""
    now = _utc_now()
    values = {
        "telegram_user_id": profile.telegram_user_id,
        "username": profile.username,
        "first_name": profile.first_name,
        "last_name": profile.last_name,
        "language_code": profile.language_code,
        "is_premium": profile.is_premium,
        "first_seen_at": now,
        "last_seen_at": now,
        "last_seen_source": source,
        "created_at": now,
        "updated_at": now,
    }
    insert_stmt = _user_insert().values(**values)
    stmt = insert_stmt.on_conflict_do_update(
        index_elements=[User.telegram_user_id],
        set_={
            "username": insert_stmt.excluded.username,
            "first_name": insert_stmt.excluded.first_name,
            "last_name": insert_stmt.excluded.last_name,
            "language_code": insert_stmt.excluded.language_code,
            "is_premium": insert_stmt.excluded.is_premium,
            "last_seen_at": now,
            "last_seen_source": source,
            "updated_at": now,
        },
    )
    async with get_async_session() as session:
        await session.execute(stmt)


async def record_forecast_request(
    *,
    telegram_user_id: int,
    source: UserSource,
    query_city: str,
    days: int,
    status: ForecastRequestStatus,
    resolved_city: str | None = None,
    http_status: int | None = None,
    error_detail: str | None = None,
) -> None:
    """Добавляет строку в forecast_requests."""
    row = ForecastRequest(
        telegram_user_id=telegram_user_id,
        source=source,
        query_city=query_city.strip()[:100],
        resolved_city=resolved_city.strip()[:100] if resolved_city else None,
        days=days,
        status=status,
        http_status=http_status,
        error_detail=_truncate_error_detail(error_detail),
        created_at=_utc_now(),
    )
    async with get_async_session() as session:
        session.add(row)


async def upsert_user_safe(profile: UserProfile, *, source: UserSource) -> None:
    """Best-effort upsert: ошибки БД только в лог, без проброса."""
    try:
        await upsert_user(profile, source=source)
    except Exception:
        logger.exception(
            "upsert_user: ошибка БД telegram_user_id=%s source=%s",
            profile.telegram_user_id,
            source,
        )


async def record_forecast_request_safe(
    *,
    telegram_user_id: int,
    source: UserSource,
    query_city: str,
    days: int,
    status: ForecastRequestStatus,
    resolved_city: str | None = None,
    http_status: int | None = None,
    error_detail: str | None = None,
) -> None:
    """Best-effort запись попытки прогноза."""
    try:
        await record_forecast_request(
            telegram_user_id=telegram_user_id,
            source=source,
            query_city=query_city,
            days=days,
            status=status,
            resolved_city=resolved_city,
            http_status=http_status,
            error_detail=error_detail,
        )
    except Exception:
        logger.exception(
            "record_forecast_request: ошибка БД telegram_user_id=%s source=%s status=%s",
            telegram_user_id,
            source,
            status,
        )
