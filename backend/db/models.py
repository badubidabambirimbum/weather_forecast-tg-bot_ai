"""ORM-модели PostgreSQL: пользователи и история запросов прогноза."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, SmallInteger, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базовый класс declarative-моделей."""


class User(Base):
    """Профиль пользователя Telegram (upsert при session и командах бота)."""

    __tablename__ = "users"

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_premium: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_source: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    forecast_requests: Mapped[list[ForecastRequest]] = relationship(back_populates="user")

    __table_args__ = (Index("ix_users_last_seen_at", last_seen_at.desc()),)


class ForecastRequest(Base):
    """Попытка запроса прогноза (успех или ошибка) из Mini App или бота."""

    __tablename__ = "forecast_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    query_city: Mapped[str] = mapped_column(String(100), nullable=False)
    resolved_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    days: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    http_status: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="forecast_requests")

    __table_args__ = (
        Index("ix_forecast_requests_user_created", telegram_user_id, created_at.desc()),
        Index("ix_forecast_requests_status_created", status, created_at.desc()),
    )
