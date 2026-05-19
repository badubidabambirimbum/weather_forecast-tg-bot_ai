"""Async SQLAlchemy engine и фабрика сессий (PostgreSQL + asyncpg)."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

load_dotenv()

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_database_url() -> str:
    """Читает DATABASE_URL из окружения (postgresql+asyncpg://...)."""
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    return url


def is_engine_initialized() -> bool:
    """True, если init_engine уже вызывался."""
    return _engine is not None


def init_engine(*, database_url: str | None = None, echo: bool = False) -> AsyncEngine:
    """Создаёт async engine и sessionmaker (идемпотентно при повторном вызове)."""
    global _engine, _session_factory
    if _engine is not None:
        return _engine

    url = (database_url or get_database_url()).strip()
    _engine = create_async_engine(url, echo=echo, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    logger.info("SQLAlchemy engine инициализирован")
    return _engine


async def dispose_engine() -> None:
    """Закрывает пул соединений при остановке приложения."""
    global _engine, _session_factory
    if _engine is None:
        return
    await _engine.dispose()
    _engine = None
    _session_factory = None
    logger.info("SQLAlchemy engine остановлен")


def _require_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database engine is not initialized; call init_engine() first")
    return _session_factory


@asynccontextmanager
async def get_async_session() -> AsyncIterator[AsyncSession]:
    """Контекстный менеджер сессии с commit/rollback."""
    factory = _require_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_connection() -> bool:
    """Проверка доступности БД (SELECT 1)."""
    if _engine is None:
        return False
    try:
        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("Проверка подключения к БД не удалась")
        return False
