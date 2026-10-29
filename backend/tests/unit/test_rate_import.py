"""Unit tests for the rate importer."""
from __future__ import annotations

from pathlib import Path

import pytest

from api.db.models import RateEdition, RateItem
from api.services.rate_import import (
    ImportError_,
    import_from_yaml,
    normalise_unit,
)

SAMPLE_DSR = (
    Path(__file__).resolve().parents[2] / "data" / "cpwd_dsr_2023" / "sample.yaml"
)


# ------------------------------------------------------------------ units
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("cum", "m3"),
        ("Cu.M.", "m3"),
        ("sqm", "m2"),
        ("Sq.m", "m2"),
        ("rmt", "m"),
        ("No.", "nos"),
        ("kg", "kg"),
    ],
)
def test_normalise_unit_maps_variants(raw, expected):
    assert normalise_unit(raw) == expected


def test_normalise_unit_rejects_unknown():
    with pytest.raises(ValueError):
        normalise_unit("furlong")


# ---------------------------------------------------------- yaml fixture import
def test_import_sample_dsr_round_trip(db_session):
    edition = import_from_yaml(db_session, SAMPLE_DSR)
    assert isinstance(edition, RateEdition)
    assert edition.source == "CPWD DSR"
    assert edition.region == "Delhi"
    assert edition.year == 2023
    items = db_session.query(RateItem).filter_by(edition_id=edition.id).all()
    assert len(items) >= 50
    # Every row has a positive rate and a normalised unit.
    for i in items:
        assert i.rate > 0
        assert i.unit in {"m", "m2", "m3", "kg", "nos", "l", "q", "t"}


def test_import_rejects_duplicate_edition(db_session):
    import_from_yaml(db_session, SAMPLE_DSR)
    with pytest.raises(ImportError_):
        import_from_yaml(db_session, SAMPLE_DSR)


def test_import_rejects_malformed_fixture(db_session, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
edition: {source: Test, region: X, year: 2020}
items:
  - {item_no: "1.1", chapter: "A", description: "foo", unit: m3, rate: 100}
  - {item_no: "1.1", chapter: "A", description: "foo again", unit: m3, rate: 200}
  - {item_no: "1.2", chapter: "A", description: "", unit: m3, rate: 100}
  - {item_no: "1.3", chapter: "A", description: "neg", unit: m3, rate: -5}
""",
        encoding="utf-8",
    )
    with pytest.raises(ImportError_) as exc:
        import_from_yaml(db_session, bad)
    reasons = exc.value.reasons
    assert any("duplicate" in r for r in reasons)
    assert any("empty description" in r for r in reasons)
    assert any("non-positive rate" in r for r in reasons)
