"""Estimates: create, read, list BOQ, override a line."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.auth import ApiKeyDep
from api.db.models import BOQLine, Estimate, Organization, Project, User
from api.deps import current_tenant, get_db
from api.schemas.boq import BOQLineOut, BOQLinePatch, EstimateOut
from api.schemas.project import EstimateCreate
from api.services.boq_persist import persist_building_params

router = APIRouter(tags=["estimates"], dependencies=[ApiKeyDep])


def _get_project(db: Session, project_id: str, org_id: str) -> Project:
    p = db.query(Project).filter(Project.id == project_id, Project.org_id == org_id).one_or_none()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return p


def _get_estimate(db: Session, estimate_id: str, org_id: str) -> Estimate:
    e = (
        db.query(Estimate)
        .join(Project, Project.id == Estimate.project_id)
        .filter(Estimate.id == estimate_id, Project.org_id == org_id)
        .one_or_none()
    )
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "estimate not found")
    return e


# ------------------------------------------------------------------ create
@router.post(
    "/projects/{project_id}/estimates",
    response_model=EstimateOut,
    status_code=status.HTTP_201_CREATED,
)
def create_estimate(
    project_id: str,
    payload: EstimateCreate,
    db: Session = Depends(get_db),
    tenant: tuple[Organization, User] = Depends(current_tenant),
) -> EstimateOut:
    org, _ = tenant
    project = _get_project(db, project_id, org.id)

    if payload.params is None and not payload.text_brief:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "provide either `params` or `text_brief`",
        )
    if payload.text_brief and payload.params is None:
        # Intake agent lands in W11. Until then, a brief alone is 422.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "text brief parsing is not yet available (W11+). Supply `params` instead.",
        )

    est = Estimate(
        project_id=project.id,
        version=1,
        status="draft",
        rate_edition_id=payload.rate_edition_id,
        cost_index=payload.cost_index,
    )
    db.add(est)
    db.commit()
    db.refresh(est)
    persist_building_params(
        db,
        estimate=est,
        params=payload.params.model_dump(),
        source=payload.params.source,
    )
    return EstimateOut.model_validate(est, from_attributes=True)


@router.get("/estimates/{estimate_id}", response_model=EstimateOut)
def get_estimate(
    estimate_id: str,
    db: Session = Depends(get_db),
    tenant: tuple[Organization, User] = Depends(current_tenant),
) -> EstimateOut:
    org, _ = tenant
    return EstimateOut.model_validate(_get_estimate(db, estimate_id, org.id), from_attributes=True)


@router.get("/estimates/{estimate_id}/params")
def get_estimate_params(
    estimate_id: str,
    db: Session = Depends(get_db),
    tenant: tuple[Organization, User] = Depends(current_tenant),
) -> dict:
    """Return the BuildingParams this estimate was created with (inputs + confidence)."""
    from api.db.models import BuildingParams as BuildingParamsRow

    org, _ = tenant
    est = _get_estimate(db, estimate_id, org.id)
    bp = db.query(BuildingParamsRow).filter_by(estimate_id=est.id).one_or_none()
    if bp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no params attached")
    return {"inputs": bp.inputs, "confidence": bp.confidence, "source": bp.source}


# ------------------------------------------------------------------ BOQ grid
@router.get("/estimates/{estimate_id}/boq", response_model=list[BOQLineOut])
def list_boq_lines(
    estimate_id: str,
    db: Session = Depends(get_db),
    tenant: tuple[Organization, User] = Depends(current_tenant),
) -> list[BOQLineOut]:
    org, _ = tenant
    est = _get_estimate(db, estimate_id, org.id)
    lines = sorted(est.boq_lines, key=lambda ln: (ln.element, ln.seq))
    return [BOQLineOut.model_validate(ln, from_attributes=True) for ln in lines]


# ------------------------------------------------------------------ override
@router.patch("/estimates/{estimate_id}/boq/{line_id}", response_model=BOQLineOut)
def patch_boq_line(
    estimate_id: str,
    line_id: str,
    patch: BOQLinePatch,
    db: Session = Depends(get_db),
    tenant: tuple[Organization, User] = Depends(current_tenant),
) -> BOQLineOut:
    org, _ = tenant
    est = _get_estimate(db, estimate_id, org.id)
    line = db.query(BOQLine).filter_by(id=line_id, estimate_id=est.id).one_or_none()
    if line is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "line not found")

    if patch.qty is not None:
        line.qty = patch.qty
    if patch.rate is not None:
        line.rate = patch.rate
    line.override_reason = patch.override_reason
    line.is_overridden = True
    line.amount = round((line.qty or 0.0) * (line.rate or 0.0), 2)

    # Recompute totals, preserving the markup percentages used at run time.
    subtotal = round(sum((ln.amount or 0.0) for ln in est.boq_lines), 2)
    contingency = round(subtotal * (est.contingency_pct or 0.0) / 100.0, 2)
    prelims = round(subtotal * (est.prelims_pct or 0.0) / 100.0, 2)
    est.total_cost = round(subtotal + contingency + prelims, 2)
    totals: dict[str, float] = {}
    for ln in est.boq_lines:
        totals[ln.element] = round(totals.get(ln.element, 0.0) + (ln.amount or 0.0), 2)
    est.totals_by_element = totals

    db.commit()
    db.refresh(line)
    return BOQLineOut.model_validate(line, from_attributes=True)
