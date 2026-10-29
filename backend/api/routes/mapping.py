"""Rate-mapping agent routes."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agents.mapping_agent import (
    accept_proposal,
    map_estimate,
    skip_proposal,
)
from api.auth import ApiKeyDep
from api.db.models import (
    MappingProposal,
    Organization,
    RateEdition,
    User,
)
from api.deps import current_tenant, get_db
from api.routes.estimates import _get_estimate
from api.services.rate_search import ensure_fts_index

router = APIRouter(tags=["mapping"], dependencies=[ApiKeyDep])


class MapRunResponse(BaseModel):
    estimate_id: str
    edition_id: str
    strategy: str
    processed: int
    auto_applied: int
    queued: int
    cache_hits: int
    duration_s: float


class ProposalCandidate(BaseModel):
    rate_item_id: str
    item_no: str
    chapter: str
    description: str
    unit: str
    rate: float
    score: float


class ProposalOut(BaseModel):
    id: str
    boq_line_id: str
    boq_description: str
    boq_unit: str
    boq_qty: float
    boq_element: str
    confidence: float
    reason: str | None
    strategy: str
    status: str
    top_candidates: list[ProposalCandidate]
    created_at: datetime


class AcceptPayload(BaseModel):
    rate_item_id: str = Field(..., description="Must be one of the stored candidates")


# ------------------------------------------------------------------ POST /map
@router.post("/estimates/{estimate_id}/map", response_model=MapRunResponse)
def run_mapping(
    estimate_id: str,
    edition_id: str | None = None,
    db: Session = Depends(get_db),
    tenant: tuple[Organization, User] = Depends(current_tenant),
) -> MapRunResponse:
    org, _ = tenant
    est = _get_estimate(db, estimate_id, org.id)
    # Resolve the rate edition: payload > estimate attachment > first available.
    eid = edition_id or est.rate_edition_id
    if not eid:
        first = db.query(RateEdition).first()
        if first is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "no rate edition available — import a DSR first",
            )
        eid = first.id

    ensure_fts_index(db)
    # Persist edition on the estimate so later runs are reproducible.
    if est.rate_edition_id != eid:
        est.rate_edition_id = eid
        db.commit()

    result = map_estimate(db, est, edition_id=eid, org_id=org.id)

    # Recompute totals (apply_mapping touches line rates/amounts).
    _recompute_totals(db, est)

    return MapRunResponse(
        estimate_id=result.estimate_id,
        edition_id=result.edition_id,
        strategy=result.strategy,
        processed=result.processed,
        auto_applied=result.auto_applied,
        queued=result.queued,
        cache_hits=result.cache_hits,
        duration_s=round(result.duration_s, 2),
    )


# ------------------------------------------------------------- GET queue
@router.get("/estimates/{estimate_id}/mapping-queue", response_model=list[ProposalOut])
def list_queue(
    estimate_id: str,
    db: Session = Depends(get_db),
    tenant: tuple[Organization, User] = Depends(current_tenant),
) -> list[ProposalOut]:
    org, _ = tenant
    est = _get_estimate(db, estimate_id, org.id)
    rows = (
        db.query(MappingProposal)
        .filter(
            MappingProposal.estimate_id == est.id,
            MappingProposal.status == "pending",
        )
        .order_by(MappingProposal.created_at.asc())
        .all()
    )
    return [_to_out(db, p) for p in rows]


# ------------------------------------------------------------- POST accept
@router.post("/estimates/{estimate_id}/mapping/{proposal_id}", response_model=ProposalOut)
def accept(
    estimate_id: str,
    proposal_id: str,
    payload: AcceptPayload,
    db: Session = Depends(get_db),
    tenant: tuple[Organization, User] = Depends(current_tenant),
) -> ProposalOut:
    org, user = tenant
    est = _get_estimate(db, estimate_id, org.id)
    prop = (
        db.query(MappingProposal)
        .filter_by(id=proposal_id, estimate_id=est.id)
        .one_or_none()
    )
    if prop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "proposal not found")
    try:
        accept_proposal(
            db,
            proposal=prop,
            rate_item_id=payload.rate_item_id,
            org_id=org.id,
            user_id=user.id,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    return _to_out(db, prop)


@router.delete("/estimates/{estimate_id}/mapping/{proposal_id}", response_model=ProposalOut)
def skip(
    estimate_id: str,
    proposal_id: str,
    db: Session = Depends(get_db),
    tenant: tuple[Organization, User] = Depends(current_tenant),
) -> ProposalOut:
    org, _ = tenant
    est = _get_estimate(db, estimate_id, org.id)
    prop = (
        db.query(MappingProposal)
        .filter_by(id=proposal_id, estimate_id=est.id)
        .one_or_none()
    )
    if prop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "proposal not found")
    skip_proposal(db, prop)
    return _to_out(db, prop)


# ------------------------------------------------------------- helpers
def _to_out(db: Session, p: MappingProposal) -> ProposalOut:
    from api.db.models import BOQLine

    line = db.query(BOQLine).filter_by(id=p.boq_line_id).one()
    return ProposalOut(
        id=p.id,
        boq_line_id=p.boq_line_id,
        boq_description=line.description,
        boq_unit=line.unit,
        boq_qty=line.qty,
        boq_element=line.element,
        confidence=p.confidence,
        reason=p.reason,
        strategy=p.strategy,
        status=p.status,
        top_candidates=[ProposalCandidate(**c) for c in (p.top_candidates or [])],
        created_at=p.created_at,
    )


def _recompute_totals(db: Session, est) -> None:
    subtotal = round(sum((ln.amount or 0.0) for ln in est.boq_lines), 2)
    cont = round(subtotal * (est.contingency_pct or 0.0) / 100.0, 2)
    prelim = round(subtotal * (est.prelims_pct or 0.0) / 100.0, 2)
    est.total_cost = round(subtotal + cont + prelim, 2)
    totals: dict[str, float] = {}
    for ln in est.boq_lines:
        totals[ln.element] = round(totals.get(ln.element, 0.0) + (ln.amount or 0.0), 2)
    est.totals_by_element = totals
    db.commit()
