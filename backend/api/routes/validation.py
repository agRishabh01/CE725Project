"""Validation + benchmark routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth import ApiKeyDep
from api.db.models import BOQLine, BuildingParams, Estimate, Organization, User
from api.deps import current_tenant, get_db
from api.routes.estimates import _get_estimate
from api.services.validation import Gate2Report, list_cases, load_case, run_all, run_case

router = APIRouter(tags=["validation"], dependencies=[ApiKeyDep])


class ElementVarianceOut(BaseModel):
    element: str
    expected_inr: float
    computed_inr: float
    delta_inr: float
    delta_pct: float


class CaseReportOut(BaseModel):
    case_id: str
    split: str
    source: str
    expected_total_inr: float
    computed_total_inr: float
    total_delta_pct: float
    cost_per_m2_expected: float
    cost_per_m2_computed: float
    element_variance: list[ElementVarianceOut]
    element_weighted_abs_error_pct: float
    pass_total: bool
    pass_element: bool


class Gate2ReportOut(BaseModel):
    cases: list[CaseReportOut]
    median_total_abs_pct: float
    median_element_weighted_pct: float
    all_calibration_within_20: bool
    all_held_out_within_25: bool
    passed: bool


def _case_to_out(c) -> CaseReportOut:
    return CaseReportOut(
        case_id=c.case_id, split=c.split, source=c.source,
        expected_total_inr=c.expected_total_inr,
        computed_total_inr=c.computed_total_inr,
        total_delta_pct=c.total_delta_pct,
        cost_per_m2_expected=c.cost_per_m2_expected,
        cost_per_m2_computed=c.cost_per_m2_computed,
        element_variance=[
            ElementVarianceOut(
                element=e.element, expected_inr=e.expected_inr,
                computed_inr=e.computed_inr, delta_inr=e.delta_inr,
                delta_pct=e.delta_pct,
            ) for e in c.element_variance
        ],
        element_weighted_abs_error_pct=c.element_weighted_abs_error_pct,
        pass_total=c.pass_total, pass_element=c.pass_element,
    )


# -------------------------------------------------------- Gate 2
@router.get("/validation/gate2", response_model=Gate2ReportOut)
def gate2_report() -> Gate2ReportOut:
    """Full Gate 2 report across every reference under data/references/."""
    r: Gate2Report = run_all()
    return Gate2ReportOut(
        cases=[_case_to_out(c) for c in r.cases],
        median_total_abs_pct=r.median_total_abs_pct,
        median_element_weighted_pct=r.median_element_weighted_pct,
        all_calibration_within_20=r.all_calibration_within_20,
        all_held_out_within_25=r.all_held_out_within_25,
        passed=r.passed,
    )


# -------------------------------------------------------- Per-estimate benchmarks
class BenchmarkOut(BaseModel):
    builtup_m2: float
    total_inr: float
    cost_per_m2: float
    concrete_m3_per_m2: float | None
    steel_kg_per_m2: float | None


@router.get("/estimates/{estimate_id}/benchmarks", response_model=BenchmarkOut)
def estimate_benchmarks(
    estimate_id: str,
    db: Session = Depends(get_db),
    tenant: tuple[Organization, User] = Depends(current_tenant),
) -> BenchmarkOut:
    org, _ = tenant
    est = _get_estimate(db, estimate_id, org.id)
    bp = db.query(BuildingParams).filter_by(estimate_id=est.id).one_or_none()
    if bp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no params on this estimate")
    builtup = float(bp.inputs.get("builtup_area_m2") or 0.0)
    if builtup <= 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "built-up area must be positive")

    total = float(est.total_cost or 0.0)
    cpm = total / builtup if total else 0.0

    concrete_m3 = 0.0
    steel_kg = 0.0
    for line in est.boq_lines:
        desc = (line.description or "").lower()
        if "rcc" in desc or "cement concrete" in desc or "pcc" in desc:
            if line.unit == "m3":
                concrete_m3 += float(line.qty or 0.0)
        if "steel" in desc and line.unit == "kg":
            steel_kg += float(line.qty or 0.0)

    return BenchmarkOut(
        builtup_m2=round(builtup, 2),
        total_inr=round(total, 2),
        cost_per_m2=round(cpm, 2),
        concrete_m3_per_m2=round(concrete_m3 / builtup, 3) if builtup else None,
        steel_kg_per_m2=round(steel_kg / builtup, 2) if builtup else None,
    )


# -------------------------------------------------------- Reference list
class ReferenceCaseOut(BaseModel):
    case_id: str
    split: str
    source: str
    expected_total_inr: float
    cost_per_m2_expected: float


@router.get("/validation/cases", response_model=list[ReferenceCaseOut])
def list_reference_cases() -> list[ReferenceCaseOut]:
    out: list[ReferenceCaseOut] = []
    for p in list_cases():
        c = load_case(p)
        bp = c["building_params"]
        exp = c["expected"]
        builtup = float(bp["builtup_area_m2"])
        out.append(ReferenceCaseOut(
            case_id=c["case_id"], split=c.get("split", "calibration"),
            source=c.get("source", ""),
            expected_total_inr=float(exp["total_inr"]),
            cost_per_m2_expected=round(float(exp["total_inr"]) / builtup, 2),
        ))
    return out
