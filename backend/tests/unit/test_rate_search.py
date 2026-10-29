"""Hybrid search over FTS5 + pseudo-embeddings on the sample DSR."""
from __future__ import annotations

from pathlib import Path

import pytest

from api.services.rate_import import import_from_yaml
from api.services.rate_search import (
    compute_and_store_embeddings,
    ensure_fts_index,
    search_rates,
)

SAMPLE_DSR = (
    Path(__file__).resolve().parents[2] / "data" / "cpwd_dsr_2023" / "sample.yaml"
)


@pytest.fixture
def loaded_edition(db_session):
    edition = import_from_yaml(db_session, SAMPLE_DSR)
    ensure_fts_index(db_session)
    compute_and_store_embeddings(db_session, edition.id)
    return edition


def test_search_returns_relevant_results(db_session, loaded_edition):
    hits = search_rates(
        db_session,
        query="RCC M25 in columns",
        edition_id=loaded_edition.id,
        unit="m3",
        limit=5,
    )
    assert hits, "expected at least one hit"
    # The ground-truth item "2.2.2" is RCC M25 in columns.
    assert any(h.item_no == "2.2.2" for h in hits[:3]), [h.item_no for h in hits]


def test_search_respects_unit_filter(db_session, loaded_edition):
    hits_m2 = search_rates(
        db_session, query="plaster", edition_id=loaded_edition.id, unit="m2", limit=10
    )
    assert hits_m2
    assert all(h.unit == "m2" for h in hits_m2)


def test_search_scores_are_normalised(db_session, loaded_edition):
    hits = search_rates(
        db_session, query="brick", edition_id=loaded_edition.id, limit=5
    )
    for h in hits:
        assert 0.0 <= h.bm25_score <= 1.0 + 1e-6
        # cosine with pseudo-embeddings is non-negative when any token overlaps.
        assert -1.0 - 1e-6 <= h.cosine_score <= 1.0 + 1e-6


def test_empty_fts_returns_empty_or_vector_fallback(db_session, loaded_edition):
    hits = search_rates(
        db_session, query="xyznothere", edition_id=loaded_edition.id, limit=3
    )
    # Empty keyword hit list → vector fallback kicks in but no term overlaps
    # with a pseudo-embedding, so every cosine is 0 and no hits bubble up.
    # Either empty or all-zero-score is acceptable here.
    assert all(h.combined_score == pytest.approx(0.0, abs=1e-6) for h in hits)
