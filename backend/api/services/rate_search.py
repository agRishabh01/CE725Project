"""Hybrid rate-item search.

Two dialect-specific paths behind one `search_rates` entry point:

**Postgres (dev + prod):**
  - Keyword leg:  `description_tsv @@ plainto_tsquery(...)` ranked by `ts_rank_cd`.
  - Vector leg:   `embedding <=> :q_vec` (cosine distance from pgvector).
  - Both indexes are created in migration 0004.

**SQLite (test fixtures only):**
  - Keyword leg:  FTS5 virtual table over `rate_item.description`.
  - Vector leg:   in-memory cosine over the BLOB column.

Caller gets a merged, re-ranked list capped at `limit`. Both legs filter
by `edition_id` and optionally by `unit` / `chapter`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.db.models import RateItem
from api.db.types import EMBED_DIM

from .embeddings import cosine, embed_texts, from_blob

FTS_TABLE = "rate_item_fts"


# ------------------------------------------------------------- schema (per-session)
def ensure_fts_index(session: Session) -> None:
    """Build or refresh the SQLite FTS5 shadow table.

    Idempotent: safe to call on every API boot or after an import.
    On Postgres this is a no-op — the `description_tsv` column maintained by
    the migration's trigger is the authoritative keyword index.
    """
    bind = session.get_bind()
    if bind.dialect.name != "sqlite":
        return
    session.execute(text(f"DROP TABLE IF EXISTS {FTS_TABLE}"))
    session.execute(
        text(
            f"""
            CREATE VIRTUAL TABLE {FTS_TABLE}
            USING fts5(item_id UNINDEXED, edition_id UNINDEXED, description,
                       chapter UNINDEXED, unit UNINDEXED, tokenize='porter')
            """
        )
    )
    rows = session.query(
        RateItem.id, RateItem.edition_id, RateItem.description,
        RateItem.chapter, RateItem.unit,
    ).all()
    if not rows:
        session.commit()
        return
    session.execute(
        text(
            f"INSERT INTO {FTS_TABLE}(item_id, edition_id, description, chapter, unit) "
            f"VALUES (:id, :edition_id, :description, :chapter, :unit)"
        ),
        [
            {
                "id": r.id, "edition_id": r.edition_id,
                "description": r.description, "chapter": r.chapter or "", "unit": r.unit,
            }
            for r in rows
        ],
    )
    session.commit()


# ------------------------------------------------------------- result shape
@dataclass(frozen=True, slots=True)
class SearchHit:
    item_id: str
    item_no: str
    chapter: str
    description: str
    unit: str
    rate: float
    bm25_score: float          # keyword relevance (normalised 0-1)
    cosine_score: float        # vector similarity (0-1 after cosine distance → sim)
    combined_score: float


# ------------------------------------------------------------- hybrid search
def search_rates(
    session: Session,
    *,
    query: str,
    edition_id: str,
    unit: str | None = None,
    chapter: str | None = None,
    limit: int = 10,
    keyword_weight: float = 0.5,
    query_vector: np.ndarray | None = None,
) -> list[SearchHit]:
    """Hybrid keyword + cosine search within one rate edition.

    `query_vector` is an optional precomputed L2-normalised float32 embedding.
    Pass it when calling in a loop (e.g. mapping agent over N BOQ lines) so
    one batched OpenRouter call covers everything instead of N round-trips.
    """
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        return _search_postgres(
            session, query=query, edition_id=edition_id,
            unit=unit, chapter=chapter, limit=limit, keyword_weight=keyword_weight,
            query_vector=query_vector,
        )
    return _search_sqlite(
        session, query=query, edition_id=edition_id,
        unit=unit, chapter=chapter, limit=limit, keyword_weight=keyword_weight,
        query_vector=query_vector,
    )


# ------------------------------------------------------------- Postgres path
_WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def _build_tsquery(query: str) -> str:
    """OR-join alnum tokens so queries using abbreviations ("RCC M25 columns")
    still match descriptions that spell them out ("Reinforced cement concrete M25
    in columns") on the shared tokens. `plainto_tsquery`'s implicit AND would
    zero this match out entirely."""
    tokens = [t.lower() for t in _WORD_RE.findall(query) if len(t) > 1]
    if not tokens:
        return "''"
    return " | ".join(tokens)


def _search_postgres(
    session: Session, *, query: str, edition_id: str,
    unit: str | None, chapter: str | None,
    limit: int, keyword_weight: float,
    query_vector: np.ndarray | None = None,
) -> list[SearchHit]:
    q_vec_arr = query_vector if query_vector is not None else next(iter(embed_texts([query])))
    q_vec = q_vec_arr.astype(np.float32).tolist()

    where = ["edition_id = :eid"]
    params: dict = {
        "eid": edition_id, "limit": limit,
        "tsq": _build_tsquery(query), "q_vec": q_vec,
    }
    if unit:
        where.append("unit = :unit")
        params["unit"] = unit
    if chapter:
        where.append("chapter = :chapter")
        params["chapter"] = chapter
    where_sql = " AND ".join(where)

    # Pull a wider pool for merging: top-N by keyword ∪ top-N by cosine.
    pool_sql = text(
        f"""
        WITH kw AS (
          SELECT id,
                 ts_rank_cd(description_tsv, to_tsquery('english', :tsq)) AS kw_score
          FROM rate_item
          WHERE {where_sql}
            AND description_tsv @@ to_tsquery('english', :tsq)
          ORDER BY kw_score DESC
          LIMIT :pool_limit
        ),
        vec AS (
          SELECT id,
                 1.0 - (embedding <=> (:q_vec)::vector) AS cos_score
          FROM rate_item
          WHERE {where_sql}
            AND embedding IS NOT NULL
          ORDER BY embedding <=> (:q_vec)::vector
          LIMIT :pool_limit
        ),
        pool AS (
          SELECT id FROM kw
          UNION
          SELECT id FROM vec
        )
        SELECT ri.id, ri.item_no, ri.chapter, ri.description,
               ri.unit, ri.rate,
               COALESCE(kw.kw_score, 0.0)  AS kw_score,
               COALESCE(vec.cos_score, 0.0) AS cos_score
        FROM pool
        JOIN rate_item ri ON ri.id = pool.id
        LEFT JOIN kw  ON kw.id  = ri.id
        LEFT JOIN vec ON vec.id = ri.id
        """
    )
    params["pool_limit"] = max(limit * 3, 30)

    rows = session.execute(pool_sql, params).all()
    if not rows:
        return []

    kw_max = max((float(r.kw_score) for r in rows), default=0.0)
    hits: list[SearchHit] = []
    for r in rows:
        kw = float(r.kw_score) / kw_max if kw_max > 0 else 0.0
        cs = float(r.cos_score)
        if kw_max > 0:
            combined = keyword_weight * kw + (1 - keyword_weight) * cs
        else:
            # No keyword hits anywhere in the pool — lean fully on the cosine
            # score so a strong semantic match can still auto-apply.
            combined = cs
        # When both legs agree strongly, bump combined up — this restores the
        # "exclusivity" signal that the deterministic agent uses for confidence.
        if kw >= 0.95 and cs >= 0.6:
            combined = min(1.0, combined + 0.15)
        hits.append(SearchHit(
            item_id=r.id, item_no=r.item_no, chapter=r.chapter or "",
            description=r.description, unit=r.unit, rate=float(r.rate),
            bm25_score=round(kw, 4), cosine_score=round(cs, 4),
            combined_score=round(combined, 4),
        ))
    hits.sort(key=lambda h: h.combined_score, reverse=True)
    return hits[:limit]


# ------------------------------------------------------------- SQLite path
def _fts_quote(query: str) -> str:
    tokens = [t for t in query.lower().split() if any(c.isalnum() for c in t)]
    if not tokens:
        return '""'
    cleaned = ["".join(c for c in t if c.isalnum()) for t in tokens]
    return " OR ".join(f'"{t}"' for t in cleaned if t)


def _search_sqlite(
    session: Session, *, query: str, edition_id: str,
    unit: str | None, chapter: str | None,
    limit: int, keyword_weight: float,
    query_vector: np.ndarray | None = None,
) -> list[SearchHit]:
    fts_q = _fts_quote(query)
    sql = (
        f"SELECT item_id, bm25({FTS_TABLE}) AS rank "
        f"FROM {FTS_TABLE} WHERE {FTS_TABLE} MATCH :q AND edition_id = :eid"
    )
    params = {"q": fts_q, "eid": edition_id}
    if unit:
        sql += " AND unit = :unit"
        params["unit"] = unit
    if chapter:
        sql += " AND chapter = :chapter"
        params["chapter"] = chapter
    sql += " ORDER BY rank LIMIT :limit"
    params["limit"] = max(limit * 3, 30)
    bm25_rows = session.execute(text(sql), params).all()
    bm25_by_id = {row.item_id: -float(row.rank) for row in bm25_rows}

    q_vec = query_vector if query_vector is not None else next(iter(embed_texts([query])))
    item_ids = list(bm25_by_id)
    if not item_ids:
        candidates = session.query(RateItem).filter(RateItem.edition_id == edition_id)
        if unit:
            candidates = candidates.filter(RateItem.unit == unit)
        if chapter:
            candidates = candidates.filter(RateItem.chapter == chapter)
        rows = candidates.limit(1000).all()
    else:
        rows = session.query(RateItem).filter(RateItem.id.in_(item_ids)).all()

    cosine_by_id: dict[str, float] = {}
    for r in rows:
        if r.embedding is None:
            cosine_by_id[r.id] = 0.0
            continue
        vec = r.embedding if hasattr(r.embedding, "shape") else from_blob(r.embedding)
        if getattr(vec, "shape", (0,))[0] != EMBED_DIM:
            cosine_by_id[r.id] = 0.0
            continue
        cosine_by_id[r.id] = cosine(q_vec, vec)

    all_ids = set(bm25_by_id) | set(cosine_by_id)
    bm25_max = max(bm25_by_id.values(), default=1.0) or 1.0
    hits: list[SearchHit] = []
    rate_items = {r.id: r for r in rows}
    for item_id in all_ids:
        r = rate_items.get(item_id)
        if r is None:
            continue
        bm = bm25_by_id.get(item_id, 0.0)
        bm_scaled = bm / bm25_max if bm25_max else 0.0
        cs = cosine_by_id.get(item_id, 0.0)
        combined = keyword_weight * bm_scaled + (1 - keyword_weight) * cs
        hits.append(SearchHit(
            item_id=r.id, item_no=r.item_no, chapter=r.chapter or "",
            description=r.description, unit=r.unit, rate=float(r.rate),
            bm25_score=bm_scaled, cosine_score=cs, combined_score=combined,
        ))
    hits.sort(key=lambda h: h.combined_score, reverse=True)
    return hits[:limit]


# ------------------------------------------------------------- embedding publish
def compute_and_store_embeddings(session: Session, edition_id: str) -> int:
    """Fill `rate_item.embedding` for every item in an edition. Returns count."""
    items = session.query(RateItem).filter(
        RateItem.edition_id == edition_id, RateItem.embedding.is_(None)
    ).all()
    if not items:
        return 0
    texts = [i.description for i in items]
    for item, vec in zip(items, embed_texts(texts), strict=True):
        # EmbeddingVector handles bytes-vs-list conversion for the dialect.
        item.embedding = vec
    session.commit()
    return len(items)
