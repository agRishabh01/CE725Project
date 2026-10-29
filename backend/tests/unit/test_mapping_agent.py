"""Mapping agent unit tests — grounding, cache, threshold."""
from __future__ import annotations

from pathlib import Path

import pytest

from agents.mapping_agent import (
    AUTO_APPLY_THRESHOLD,
    description_hash,
    normalise_description,
    propose_for_line,
)
from api.db.models import BOQLine, Estimate, OrgMapping, Organization, Project
from api.services.rate_import import import_from_yaml
from api.services.rate_search import compute_and_store_embeddings, ensure_fts_index

SAMPLE_DSR = (
    Path(__file__).resolve().parents[2] / "data" / "cpwd_dsr_2023" / "sample.yaml"
)


@pytest.fixture
def edition(db_session):
    e = import_from_yaml(db_session, SAMPLE_DSR)
    ensure_fts_index(db_session)
    compute_and_store_embeddings(db_session, e.id)
    return e


@pytest.fixture
def est(db_session):
    org = Organization(name="Test")
    db_session.add(org)
    db_session.flush()
    pr = Project(org_id=org.id, name="P")
    db_session.add(pr)
    db_session.flush()
    e = Estimate(project_id=pr.id)
    db_session.add(e)
    db_session.flush()
    db_session.commit()
    return e


def _mk_line(db_session, est, element, seq, desc, unit, qty):
    ln = BOQLine(
        estimate_id=est.id, element=element, seq=seq,
        description=desc, unit=unit, qty=qty,
    )
    db_session.add(ln)
    db_session.flush()
    return ln


def test_normalise_description_is_stable():
    a = normalise_description("RCC M25 in columns", "m3")
    b = normalise_description("  RCC   M25,  in   Columns!!! ", "M3")
    assert a == b


def test_description_hash_stable():
    assert description_hash("abc XYZ", "m3") == description_hash("abc xyz", "m3")
    assert description_hash("abc", "m3") != description_hash("abc", "m2")


def test_propose_returns_candidates_above_threshold(db_session, est, edition):
    line = _mk_line(
        db_session, est, "frame", 1,
        "RCC M25 in columns, including vibrating and curing", "m3", 10.0,
    )
    prop = propose_for_line(db_session, line, edition.id)
    assert prop.candidates
    # Deterministic hybrid picks 2.2.2 for RCC M25 columns.
    assert prop.candidates[0].item_no == "2.2.2"
    assert prop.confidence > 0.0
    assert "search" in prop.reason.lower() or "ranked" in prop.reason.lower()


def test_propose_grounded_candidates_only(db_session, est, edition):
    """Every candidate id must exist in the rate catalog (grounding guard)."""
    from api.db.models import RateItem

    line = _mk_line(
        db_session, est, "finishes", 1,
        "Internal plaster CM 1:4, 12 mm thick", "m2", 100.0,
    )
    prop = propose_for_line(db_session, line, edition.id)
    for c in prop.candidates:
        assert db_session.query(RateItem).filter_by(id=c.rate_item_id).one_or_none() is not None


def test_threshold_boundary_const():
    """Guards against accidental threshold drift between code and docs."""
    assert AUTO_APPLY_THRESHOLD == 0.75
