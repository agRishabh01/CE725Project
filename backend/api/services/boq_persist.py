"""Convert `PricedBOQ` (engine dataclass) → DB rows and back.

The engine stays pure (no DB imports). This module is the only place that
knows how a priced BOQ maps onto `Estimate` + `BuildingParams` + `BOQLine` rows.
"""
from __future__ import annotations

from dataclasses import asdict

from sqlalchemy.orm import Session

from api.db.models import BOQLine, BuildingParams, Estimate
from boq_engine.pricing import PricedBOQ
from boq_engine.trace import FormulaTrace


def persist_priced_boq(
    db: Session,
    *,
    estimate: Estimate,
    priced: PricedBOQ,
) -> Estimate:
    """Overwrite the BOQ lines + totals on an existing Estimate row."""
    # Replace all existing lines (cascade handles delete via relationship).
    for line in list(estimate.boq_lines):
        db.delete(line)
    db.flush()

    for ln in priced.lines:
        db.add(
            BOQLine(
                estimate_id=estimate.id,
                element=ln.element,
                seq=ln.seq,
                description=ln.description,
                unit=ln.unit,
                qty=ln.qty,
                rate=ln.rate_inr,
                amount=ln.amount_inr,
                formula_trace=_serialise_trace(ln.formula_trace),
                is_overridden=False,
            )
        )
    estimate.total_cost = priced.total_inr
    estimate.totals_by_element = priced.totals_by_element
    estimate.cost_index = priced.cost_index
    db.commit()
    db.refresh(estimate)
    return estimate


def persist_building_params(
    db: Session, *, estimate: Estimate, params: dict, confidence: dict | None = None,
    source: str = "form",
) -> BuildingParams:
    bp = (
        db.query(BuildingParams)
        .filter_by(estimate_id=estimate.id)
        .one_or_none()
    )
    if bp is None:
        bp = BuildingParams(
            estimate_id=estimate.id, inputs=params, confidence=confidence, source=source,
        )
        db.add(bp)
    else:
        bp.inputs = params
        bp.confidence = confidence
        bp.source = source
    db.commit()
    return bp


def _serialise_trace(trace: FormulaTrace | None) -> dict | None:
    if trace is None:
        return None
    return {
        "rule_id": trace.rule_id,
        "version": trace.version,
        "formula": trace.formula,
        "inputs": trace.inputs,
        "output": trace.output,
        "source": trace.source,
    }
