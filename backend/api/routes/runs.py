"""Run execution + SSE event stream.

POST /estimates/{id}/runs       Start a run; returns the run id + initial state.
GET  /runs/{run_id}/events      Server-sent events for that run.

Week 5: runs are synchronous — POST drains the generator into persistence, GET
replays the stored events. In W18 this moves to Arq + Redis pub/sub, but the
POST + GET shape stays.
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.auth import ApiKeyDep
from api.db.models import AgentRun, BuildingParams, Organization, User
from api.deps import current_tenant, get_db
from api.routes.estimates import _get_estimate
from api.schemas.project import RunCreate
from api.services.agent_runner import run_full, sse_wrap

router = APIRouter(tags=["runs"], dependencies=[ApiKeyDep])


@router.post("/estimates/{estimate_id}/runs", status_code=status.HTTP_201_CREATED)
async def create_run(
    estimate_id: str,
    payload: RunCreate,
    db: Session = Depends(get_db),
    tenant: tuple[Organization, User] = Depends(current_tenant),
) -> dict:
    org, _ = tenant
    est = _get_estimate(db, estimate_id, org.id)
    bp = db.query(BuildingParams).filter_by(estimate_id=est.id).one_or_none()
    if bp is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "estimate has no BuildingParams")

    if payload.mode != "full":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"mode={payload.mode!r} is not available until W8 (mapping agent) / W13 (report agent)",
        )

    # Drain the generator synchronously, collecting events for replay via SSE.
    events: list[dict] = []
    async for ev in run_full(db, estimate=est, params=bp.inputs, org_id=org.id):
        events.append(ev)

    # Persist the events on the run row for later SSE replay.
    run = (
        db.query(AgentRun)
        .filter_by(estimate_id=est.id, agent="orchestrator")
        .order_by(AgentRun.created_at.desc())
        .first()
    )
    if run is not None:
        out = dict(run.output or {})
        out["events"] = events
        run.output = out
        db.commit()

    return {
        "run_id": run.id if run else None,
        "estimate_id": est.id,
        "status": run.status if run else "unknown",
        "event_count": len(events),
    }


@router.get("/runs/{run_id}/events")
async def stream_events(
    run_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    run = db.query(AgentRun).filter_by(id=run_id).one_or_none()
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")

    stored_events = list((run.output or {}).get("events") or [])

    async def gen():
        for ev in stored_events:
            if await request.is_disconnected():
                break
            yield sse_wrap(ev)
            await asyncio.sleep(0)
        # Trailing heartbeat so clients know the stream closed cleanly.
        yield sse_wrap({
            "step": "stream_end", "status": "completed",
            "message": "no more events", "data": None,
            "ts": datetime.now(UTC).isoformat(),
        })

    return StreamingResponse(gen(), media_type="text/event-stream")
