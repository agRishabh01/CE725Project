"""Validation service — Gate 2 contract tests."""
from __future__ import annotations

from pathlib import Path

from api.services.validation import (
    list_cases,
    load_case,
    run_all,
    run_case,
)

REFERENCES_DIR = (
    Path(__file__).resolve().parents[2] / "data" / "references"
)


# --------------------------------------------------- individual case shape
def test_run_case_returns_structured_report():
    case = load_case(REFERENCES_DIR / "case_01_g2_residential.yaml")
    r = run_case(case)
    assert r.case_id.startswith("case_01")
    assert r.split in {"calibration", "held_out"}
    assert r.element_variance
    assert all(abs(e.delta_pct) < 1e9 for e in r.element_variance)
    assert r.cost_per_m2_computed > 0
    assert isinstance(r.pass_total, bool)


def test_calibration_cases_within_pm20():
    for p in list_cases():
        case = load_case(p)
        if case.get("split") != "calibration":
            continue
        r = run_case(case)
        assert abs(r.total_delta_pct) <= 20.0, (
            f"{r.case_id} total variance {r.total_delta_pct}% exceeds ±20%"
        )


def test_held_out_cases_within_pm25():
    for p in list_cases():
        case = load_case(p)
        if case.get("split") != "held_out":
            continue
        r = run_case(case)
        assert abs(r.total_delta_pct) <= 25.0, (
            f"{r.case_id} total variance {r.total_delta_pct}% exceeds ±25% held-out cap"
        )


# --------------------------------------------------- Gate 2
def test_gate2_passes_on_current_rules():
    """Snapshot the Gate 2 verdict. If this fails, either rules or references
    changed — review before updating."""
    r = run_all()
    assert r.passed, (
        f"Gate 2 failed: median_total={r.median_total_abs_pct}%, "
        f"median_element_weighted={r.median_element_weighted_pct}%, "
        f"calibration_ok={r.all_calibration_within_20}, "
        f"held_out_ok={r.all_held_out_within_25}"
    )
    assert r.median_total_abs_pct <= 20.0
    assert r.median_element_weighted_pct <= 20.0


def test_gate2_covers_at_least_three_cases():
    r = run_all()
    assert len(r.cases) >= 3
    splits = {c.split for c in r.cases}
    assert "calibration" in splits
    assert "held_out" in splits


def test_cases_are_discoverable():
    paths = list_cases()
    assert len(paths) >= 3
    names = [p.name for p in paths]
    assert any("case_01" in n for n in names)
    assert any("case_02" in n for n in names)
    assert any("case_03" in n for n in names)
