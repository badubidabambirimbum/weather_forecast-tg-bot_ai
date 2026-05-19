"""Интеграционные тесты PostgreSQL (опционально, нужен TEST_DATABASE_URL)."""

from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import select

from backend.db import engine as engine_module
from backend.db.engine import check_connection, dispose_engine, init_engine
from backend.db.models import User
from backend.db.repository import UserProfile, upsert_user

pytestmark = pytest.mark.integration

_TEST_DB_URL = os.getenv("TEST_DATABASE_URL", "").strip()


@pytest.fixture(scope="module")
def postgres_engine():
    """Поднимает engine к тестовой БД на время модуля."""
    if not _TEST_DB_URL:
        pytest.skip("TEST_DATABASE_URL не задан")
    init_engine(database_url=_TEST_DB_URL)
    if not asyncio.run(check_connection()):
        pytest.skip("TEST_DATABASE_URL: нет подключения")
    yield
    asyncio.run(dispose_engine())


def test_upsert_user_postgres(postgres_engine: None) -> None:
    """Smoke: upsert в реальном PostgreSQL."""

    async def _run() -> None:
        uid = 999_000_001
        await upsert_user(
            UserProfile(telegram_user_id=uid, username="integration_test"),
            source="bot",
        )
        factory = engine_module._require_session_factory()
        async with factory() as session:
            row = await session.scalar(select(User).where(User.telegram_user_id == uid))
        assert row is not None
        assert row.username == "integration_test"

    asyncio.run(_run())
