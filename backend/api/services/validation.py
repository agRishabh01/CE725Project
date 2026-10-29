"""Compare an engine estimate to a hand-authored reference.

A reference case is a YAML file under `backend/data/references/` with the
same `BuildingParams` the engine will consume, the same cost index, and
expected totals (overall + per element). The service runs the engine on the
reference's params and produces a `VarianceReport`.

Gate 2 contract (W10):
  - Median total variance across all cases ≤ ±20%.
  - Held-out cases (split: "held_out") stay inside ±25%.
  - Element-level cost-weighted error ≤ ±20%.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from boq_engine.estimate import estimate_from_params

REFERENCES_DIR = Path(__file__).resolve().parents[2] / "data" / "references"


# ------------------------------------------------------------------ types
@dataclass(frozen=True, slots=True)
class ElementVariance:
    element: str
    expected_inr: float
    computed_inr: float
    delta_inr: float
    delta_pct: float          # (computed - expected) / expected * 100


@dataclass(frozen=True, slots=True)
class CaseReport:
    case_id: str
    split: str                # "calibration" | "held_out"
    source: str
    expected_total_inr: float
    computed_total_inr: float
    total_delta_pct: float
    cost_per_m2_expected: float
    cost_per_m2_computed: float
    element_variance: list[ElementVariance]
    element_weighted_abs_error_pct: float
    pass_total: bool          # total ≤ ±20% (held-out ±25%)
    pass_element: bool        # weighted element error ≤ ±20%


@dataclass(frozen=True, slots=True)
class Gate2Report:
    cases: list[CaseReport]
    median_total_abs_pct: float
    median_element_weighted_pct: float
    all_calibration_within_20: bool
    all_held_out_within_25: bool
    passed: bool              # overall Gate 2 verdict


# ------------------------------------------------------------------ loader
def load_case(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_cases(directory: str | Path = REFERENCES_DIR) -> list[Path]:
    d = Path(directory)
    return sorted(d.glob("case_*.yaml"))


# ------------------------------------------------------------------ core
def run_case(case: dict[str, Any]) -> CaseReport:
    params = dict(case["building_params"])
    cost_index = float(case.get("cost_index", 1.0))
    expected = case["expected"]
    expected_total = float(expected["total_inr"])
    expected_by_el: dict[str, float] = {
        k: float(v) for k, v in expected["by_element"].items()
    }

    priced = estimate_from_params(params, cost_index=cost_index)
    computed_total = float(priced.total_inr)
    computed_by_el: dict[str, float] = dict(priced.totals_by_element)

    builtup = float(params["builtup_area_m2"])
    elems: list[ElementVariance] = []
    weighted_err_num = 0.0
    weighted_err_den = 0.0
    for el, exp in expected_by_el.items():
        got = computed_by_el.get(el, 0.0)
        delta = got - exp
        pct = (delta / exp) * 100.0 if exp else 0.0
        elems.append(ElementVariance(
            element=el,
            expected_inr=round(exp, 2),
            computed_inr=round(got, 2),
            delta_inr=round(delta, 2),
            delta_pct=round(pct, 2),
        ))
        weighted_err_num += exp * abs(pct)
        weighted_err_den += exp
    weighted_pct = (
        weighted_err_num / weighted_err_den if weighted_err_den else 0.0
    )

    total_pct = ((computed_total - expected_total) / expected_total) * 100.0
    split = case.get("split", "calibration")
    cap_total = 25.0 if split == "held_out" else 20.0

    return CaseReport(
        case_id=case["case_id"],
        split=split,
        source=case.get("source", ""),
        expected_total_inr=round(expected_total, 2),
        computed_total_inr=round(computed_total, 2),
        total_delta_pct=round(total_pct, 2),
        cost_per_m2_expected=round(expected_total / builtup, 2),
        cost_per_m2_computed=round(computed_total / builtup, 2),
        element_variance=elems,
        element_weighted_abs_error_pct=round(weighted_pct, 2),
        pass_total=abs(total_pct) <= cap_total,
        pass_element=weighted_pct <= 20.0,
    )


def run_all(paths: list[Path] | None = None) -> Gate2Report:
    cases = paths or list_cases()
    reports = [run_case(load_case(p)) for p in cases]
    totals_abs = [abs(r.total_delta_pct) for r in reports]
    el_pcts = [r.element_weighted_abs_error_pct for r in reports]
    median_total = statistics.median(totals_abs) if totals_abs else 0.0
    median_el = statistics.median(el_pcts) if el_pcts else 0.0
    cal_ok = all(abs(r.total_delta_pct) <= 20.0 for r in reports if r.split == "calibration")
    held_ok = all(abs(r.total_delta_pct) <= 25.0 for r in reports if r.split == "held_out")
    passed = (
        median_total <= 20.0
        and median_el <= 20.0
        and cal_ok
        and held_ok
    )
    return Gate2Report(
        cases=reports,
        median_total_abs_pct=round(median_total, 2),
        median_element_weighted_pct=round(median_el, 2),
        all_calibration_within_20=cal_ok,
        all_held_out_within_25=held_ok,
        passed=passed,
    )
