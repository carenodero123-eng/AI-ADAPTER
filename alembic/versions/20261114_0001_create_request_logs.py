"""Create request_logs.

Revision ID: 20261114_0001
Revises:
Create Date: 2026-11-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261114_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "request_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("auth_role", sa.String(length=16), nullable=True),
        sa.Column("selected_provider", sa.String(length=32), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("fallback_reason", sa.String(length=128), nullable=True),
        sa.Column("providers_tried", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("extraction", sa.String(length=16), nullable=True),
        sa.Column("extraction_reason", sa.String(length=64), nullable=True),
        sa.Column("missing_field_count", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_request_logs")),
    )
    op.create_index(
        op.f("ix_request_logs_occurred_at"),
        "request_logs",
        ["occurred_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_request_logs_request_id"),
        "request_logs",
        ["request_id"],
        unique=False,
    )
    op.create_index(
        "ix_request_logs_kind_occurred_at",
        "request_logs",
        ["kind", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_request_logs_status_occurred_at",
        "request_logs",
        ["status", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_request_logs_provider_occurred_at",
        "request_logs",
        ["provider", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_request_logs_provider_occurred_at",
        table_name="request_logs",
    )
    op.drop_index(
        "ix_request_logs_status_occurred_at",
        table_name="request_logs",
    )
    op.drop_index(
        "ix_request_logs_kind_occurred_at",
        table_name="request_logs",
    )
    op.drop_index(
        op.f("ix_request_logs_request_id"),
        table_name="request_logs",
    )
    op.drop_index(
        op.f("ix_request_logs_occurred_at"),
        table_name="request_logs",
    )
    op.drop_table("request_logs")
