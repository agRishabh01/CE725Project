"""mapping_proposal + org_mapping

Revision ID: 0003_mapping
Revises: 0002_markup_fields
Create Date: 2026-10-28
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from api.db.models import Base

revision: str = "0003_mapping"
down_revision: str | Sequence[str] | None = "0002_markup_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Reuse the declarative metadata — it already knows the new tables.
    Base.metadata.create_all(
        bind=op.get_bind(),
        tables=[
            Base.metadata.tables["mapping_proposal"],
            Base.metadata.tables["org_mapping"],
        ],
    )


def downgrade() -> None:
    op.drop_table("org_mapping")
    op.drop_table("mapping_proposal")
