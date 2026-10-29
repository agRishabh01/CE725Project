"""add contingency_pct and prelims_pct to estimate

Revision ID: 0002_markup_fields
Revises: 0001_initial
Create Date: 2026-10-28
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_markup_fields"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(bind, table: str, column: str) -> bool:
    from sqlalchemy import inspect
    return any(c["name"] == column for c in inspect(bind).get_columns(table))


def upgrade() -> None:
    # Idempotent: 0001's `Base.metadata.create_all` already applies the current
    # model shape (which includes these columns). On a true pre-W5 DB this
    # adds them; on a from-scratch W5+ DB this is a safe no-op.
    bind = op.get_bind()
    with op.batch_alter_table("estimate") as batch:
        if not _column_exists(bind, "estimate", "contingency_pct"):
            batch.add_column(sa.Column("contingency_pct", sa.Float(), nullable=False, server_default="3.0"))
        if not _column_exists(bind, "estimate", "prelims_pct"):
            batch.add_column(sa.Column("prelims_pct", sa.Float(), nullable=False, server_default="2.0"))


def downgrade() -> None:
    with op.batch_alter_table("estimate") as batch:
        batch.drop_column("prelims_pct")
        batch.drop_column("contingency_pct")
