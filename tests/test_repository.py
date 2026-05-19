"""Unit-тесты репозитория БД на SQLite in-memory (без Docker)."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.db import engine as engine_module
from backend.db.models import Base, ForecastRequest, User
from backend.db.repository import (
    UserProfile,
    record_forecast_request,
    upsert_user,
)


@pytest.fixture
def sqlite_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подменяет engine на SQLite :memory: для изоляции тестов."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async def _setup() -> async_sessionmaker:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(engine_module, "_engine", engine)
        monkeypatch.setattr(engine_module, "_session_factory", factory)
        return factory

    asyncio.run(_setup())
    yield
    asyncio.run(engine.dispose())
    monkeypatch.setattr(engine_module, "_engine", None)
    monkeypatch.setattr(engine_module, "_session_factory", None)


def test_upsert_user_inserts_and_updates_username(sqlite_db: None) -> None:
    """Первый upsert создаёт строку, второй обновляет username и last_seen_source."""

    async def _run() -> None:
        profile_v1 = UserProfile(
            telegram_user_id=1001,
            username="alice",
            first_name="Alice",
            language_code="ru",
        )
        await upsert_user(profile_v1, source="miniapp")

        profile_v2 = UserProfile(
            telegram_user_id=1001,
            username="alice_new",
            first_name="Alice",
            language_code="en",
        )
        await upsert_user(profile_v2, source="bot")

        factory = engine_module._require_session_factory()
        async with factory() as session:
            row = await session.get(User, 1001)
            assert row is not None
            assert row.username == "alice_new"
            assert row.language_code == "en"
            assert row.last_seen_source == "bot"
            assert row.first_seen_at is not None
            assert row.last_seen_at >= row.first_seen_at

    asyncio.run(_run())


def test_record_forecast_request_success_and_errors(sqlite_db: None) -> None:
    """Записываются success, validation_error и open_meteo_error."""

    async def _run() -> None:
        await upsert_user(
            UserProfile(telegram_user_id=2002, username="bob"),
            source="bot",
        )
        await record_forecast_request(
            telegram_user_id=2002,
            source="miniapp",
            query_city="Moscow",
            days=3,
            status="success",
            resolved_city="Москва",
            http_status=200,
        )
        await record_forecast_request(
            telegram_user_id=2002,
            source="miniapp",
            query_city="X",
            days=2,
            status="validation_error",
            http_status=422,
            error_detail="days must be one of: 1, 3, 10",
        )
        await record_forecast_request(
            telegram_user_id=2002,
            source="bot",
            query_city="Nowhere",
            days=3,
            status="open_meteo_error",
            http_status=400,
            error_detail="City not found",
        )

        factory = engine_module._require_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(ForecastRequest)
                .where(ForecastRequest.telegram_user_id == 2002)
                .order_by(ForecastRequest.id)
            )
            rows = list(result.scalars().all())
        assert len(rows) == 3
        assert rows[0].status == "success"
        assert rows[0].resolved_city == "Москва"
        assert rows[1].status == "validation_error"
        assert rows[1].resolved_city is None
        assert rows[2].status == "open_meteo_error"
        assert rows[2].source == "bot"

    asyncio.run(_run())
