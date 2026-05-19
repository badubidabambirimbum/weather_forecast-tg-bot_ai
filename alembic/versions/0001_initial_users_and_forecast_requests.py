"""users и forecast_requests — профиль и история запросов прогноза.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=128), nullable=True),
        sa.Column("last_name", sa.String(length=128), nullable=True),
        sa.Column("language_code", sa.String(length=16), nullable=True),
        sa.Column("is_premium", sa.Boolean(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_source", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("telegram_user_id"),
    )
    op.create_index(
        "ix_users_last_seen_at",
        "users",
        ["last_seen_at"],
        postgresql_ops={"last_seen_at": "DESC"},
    )

    op.create_table(
        "forecast_requests",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("query_city", sa.String(length=100), nullable=False),
        sa.Column("resolved_city", sa.String(length=100), nullable=True),
        sa.Column("days", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("http_status", sa.SmallInteger(), nullable=True),
        sa.Column("error_detail", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"],
            ["users.telegram_user_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_forecast_requests_user_created",
        "forecast_requests",
        ["telegram_user_id", "created_at"],
        postgresql_ops={"created_at": "DESC"},
    )
    op.create_index(
        "ix_forecast_requests_status_created",
        "forecast_requests",
        ["status", "created_at"],
        postgresql_ops={"created_at": "DESC"},
    )


def downgrade() -> None:
    op.drop_index("ix_forecast_requests_status_created", table_name="forecast_requests")
    op.drop_index("ix_forecast_requests_user_created", table_name="forecast_requests")
    op.drop_table("forecast_requests")
    op.drop_index("ix_users_last_seen_at", table_name="users")
    op.drop_table("users")
