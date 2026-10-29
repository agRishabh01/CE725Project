"""Run executor for Week 5.

Phase 2 ships a *synchronous* run: compute the engine, persist, emit a few SSE
events describing what happened. In W8 the mapping agent plugs into the same
event stream; in W18 this moves behind an Arq worker. The HTTP shape stays
stable across all three.

Events are plain dicts for easy JSON-serialisation. The SSE wire format is
built in routes/runs.py.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from agents.mapping_agent import map_estimate
from api.db.models import AgentRun, Estimate, RateEdition
from api.services.boq_persist import persist_priced_boq
from api.services.rate_search import ensure_fts_index
from boq_engine.estimate import estimate_from_params


def _event(step: str, status: str, message: str | None = None, data: dict | None = None) -> dict:
    return {
        "step": step,
        "status": status,
        "message": message,
        "data": data,
        "ts": datetime.now(UTC).isoformat(),
    }


async def run_full(
    db: Session, *, estimate: Estimate, params: dict[str, Any], org_id: str | None = None,
) -> AsyncIterator[dict]:
    """Run intake → engine → persist → mapping, yielding SSE events along the way.

    This is an async generator so the HTTP handler can stream events without
    buffering. The engine itself is synchronous and fast (< 100 ms), so we
    just `await asyncio.sleep(0)` between steps to let the event loop flush.
    """
    run = AgentRun(
        estimate_id=estimate.id,
        agent="orchestrator",
        model=None,
        input={"params": params, "mode": "full"},
        status="running",
    )
    db.add(run)
    db.commit()

    try:
        yield _event("intake", "completed",
                     message="parameters received",
                     data={"use_type": params.get("use_type"), "floors": params.get("floors")})
        await asyncio.sleep(0)

        yield _event("quantities", "running", message="running take-off")
        priced = estimate_from_params(params, cost_index=float(params.get("cost_index", 1.0)))
        yield _event("quantities", "completed", data={"line_count": len(priced.lines)})
        await asyncio.sleep(0)

        yield _event("pricing", "running")
        persist_priced_boq(db, estimate=estimate, priced=priced)
        yield _event("pricing", "completed",
                     data={
                         "subtotal_inr": priced.subtotal_inr,
                         "total_inr": priced.total_inr,
                         "cost_per_m2": round(priced.total_inr / max(params["builtup_area_m2"], 1), 2),
                     })
        await asyncio.sleep(0)

        # ---- Mapping stage (Week 8). Chains automatically when a rate edition
        # is loaded; otherwise we fall through on the spec-fallback rates.
        edition = db.query(RateEdition).order_by(RateEdition.year.desc()).first()
        if edition is not None and org_id is not None:
            ensure_fts_index(db)
            yield _event(
                "mapping", "running",
                message=f"mapping to {edition.source} {edition.year}",
                data={"edition_id": edition.id},
            )
            result = map_estimate(db, estimate, edition_id=edition.id, org_id=org_id)
            yield _event(
                "mapping", "completed",
                data={
                    "strategy": result.strategy,
                    "processed": result.processed,
                    "auto_applied": result.auto_applied,
                    "queued": result.queued,
                    "cache_hits": result.cache_hits,
                    "duration_s": round(result.duration_s, 2),
                },
            )
            # Refresh totals after mapping overwrote line rates.
            db.refresh(estimate)
            subtotal = round(sum((ln.amount or 0.0) for ln in estimate.boq_lines), 2)
            cont = round(subtotal * (estimate.contingency_pct or 0.0) / 100.0, 2)
            prelim = round(subtotal * (estimate.prelims_pct or 0.0) / 100.0, 2)
            estimate.total_cost = round(subtotal + cont + prelim, 2)
            totals: dict[str, float] = {}
            for ln in estimate.boq_lines:
                totals[ln.element] = round(totals.get(ln.element, 0.0) + (ln.amount or 0.0), 2)
            estimate.totals_by_element = totals
            db.commit()
        else:
            yield _event(
                "mapping", "completed",
                message="no rate edition loaded — using spec-fallback rates",
                data={"strategy": "spec_fallback"},
            )

        run.status = "completed"
        run.output = {
            "line_count": len(priced.lines),
            "total_inr": estimate.total_cost,
            "totals_by_element": estimate.totals_by_element,
        }
        db.commit()

        yield _event("done", "completed",
                     message="estimate ready",
                     data={"estimate_id": estimate.id, "total_inr": estimate.total_cost})
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.output = {"error": str(exc)}
        db.commit()
        yield _event("error", "failed", message=str(exc))


def sse_wrap(event: dict) -> bytes:
    """Encode one dict as a single text/event-stream message."""
    payload = json.dumps(event, default=str)
    return f"event: {event['step']}\ndata: {payload}\n\n".encode("utf-8")
