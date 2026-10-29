"""Rate-mapping eval harness.

Loads a labelled corpus of 47 BOQ-description → DSR item_no pairs, runs each
through `search_rates`, and asserts top-1 ≥ 85% and top-3 ≥ 95% on the sample
CPWD DSR fixture. These are the W8 "done when" thresholds from the plan.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.services.rate_import import import_from_yaml
from api.services.rate_search import (
    compute_and_store_embeddings,
    ensure_fts_index,
    search_rates,
)

LABELS = Path(__file__).parent / "mapping_labels.json"
SAMPLE_DSR = (
    Path(__file__).resolve().parents[2] / "data" / "cpwd_dsr_2023" / "sample.yaml"
)


@pytest.fixture(scope="module")
def labels() -> list[dict]:
    return json.loads(LABELS.read_text(encoding="utf-8"))


@pytest.fixture
def loaded(db_session):
    edition = import_from_yaml(db_session, SAMPLE_DSR)
    ensure_fts_index(db_session)
    compute_and_store_embeddings(db_session, edition.id)
    return edition


def test_mapping_precision_thresholds(db_session, loaded, labels):
    """Deterministic hybrid-search path only — LLM mode runs under
    ANTHROPIC_API_KEY and is covered by separate e2e tests."""
    top1_hits = 0
    top3_hits = 0
    missed: list[tuple[str, str, list[str]]] = []
    for row in labels:
        hits = search_rates(
            db_session,
            query=row["desc"],
            edition_id=loaded.id,
            unit=row["unit"],
            limit=5,
        )
        picked = [h.item_no for h in hits]
        expected = row["expected_item_no"]
        if picked and picked[0] == expected:
            top1_hits += 1
        if expected in picked[:3]:
            top3_hits += 1
        else:
            missed.append((row["desc"][:60], expected, picked[:3]))

    n = len(labels)
    top1 = top1_hits / n
    top3 = top3_hits / n
    report = f"\n  top-1: {top1_hits}/{n} = {top1:.1%}\n  top-3: {top3_hits}/{n} = {top3:.1%}"
    if missed:
        report += "\n  misses (top-3):\n" + "\n".join(
            f"    - {d!r}  expected={e}  got={p}" for d, e, p in missed[:10]
        )
    assert top1 >= 0.85, report
    assert top3 >= 0.95, report
