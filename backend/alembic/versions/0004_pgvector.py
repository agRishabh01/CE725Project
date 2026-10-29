"""Postgres hybrid-search infrastructure: tsvector + GIN + ivfflat.

Revision ID: 0004_pgvector
Revises: 0003_mapping
Create Date: 2026-10-29

Postgres only — SQLite tests skip this entirely. Enabling the `vector`
extension itself is handled in alembic/env.py before any migration runs,
so by the time this runs the `embedding` column is already `vector(1024)`.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_pgvector"
down_revision: str | Sequence[str] | None = "0003_mapping"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # IVFFLAT index for ANN cosine search on the native vector(1024) column.
    # 100 lists is sensible for ~3k-item DSR; tune when catalog grows past ~50k.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rate_item_embedding_cosine "
        "ON rate_item USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    # Keyword leg of hybrid search: tsvector maintained by trigger + GIN index.
    # Replaces SQLite FTS5. See api/services/rate_search.py for the query path.
    op.execute("ALTER TABLE rate_item ADD COLUMN IF NOT EXISTS description_tsv tsvector")
    op.execute(
        "UPDATE rate_item SET description_tsv = to_tsvector('english', coalesce(description, ''))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rate_item_description_tsv "
        "ON rate_item USING gin (description_tsv)"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION rate_item_tsv_update() RETURNS trigger AS $$
        BEGIN
          NEW.description_tsv := to_tsvector('english', coalesce(NEW.description, ''));
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_rate_item_tsv ON rate_item")
    op.execute(
        "CREATE TRIGGER trg_rate_item_tsv "
        "BEFORE INSERT OR UPDATE OF description ON rate_item "
        "FOR EACH ROW EXECUTE FUNCTION rate_item_tsv_update()"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS trg_rate_item_tsv ON rate_item")
    op.execute("DROP FUNCTION IF EXISTS rate_item_tsv_update")
    op.execute("DROP INDEX IF EXISTS ix_rate_item_description_tsv")
    op.execute("DROP INDEX IF EXISTS ix_rate_item_embedding_cosine")
    op.execute("ALTER TABLE rate_item DROP COLUMN IF EXISTS description_tsv")
