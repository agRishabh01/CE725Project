"""initial schema (all 12 PDR entities)

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-27

Rather than hand-roll every op.create_table, this uses Base.metadata.create_all
on the live connection. Subsequent migrations use autogenerate against this baseline.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from api.db.models import Base

revision: str = "0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
