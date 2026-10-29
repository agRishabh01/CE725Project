"""Project and run-level schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .building import BuildingParams


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    location: str | None = None
    use_type: str | None = None


class ProjectOut(BaseModel):
    id: str
    org_id: str
    name: str
    location: str | None
    use_type: str | None
    created_at: datetime


class EstimateCreate(BaseModel):
    """Create an estimate from either explicit params or a free-text brief."""

    params: BuildingParams | None = None
    text_brief: str | None = Field(default=None, max_length=4000)
    rate_edition_id: str | None = None
    cost_index: float = Field(default=1.0, ge=0.5, le=3.0)


RunMode = Literal["full", "quantities_only", "mapping_only", "report_only"]
RunStatus = Literal["pending", "running", "awaiting_user", "completed", "failed"]


class RunCreate(BaseModel):
    mode: RunMode = "full"


class RunEvent(BaseModel):
    """One SSE event in /runs/{id}/events."""

    run_id: str
    step: str
    status: RunStatus
    message: str | None = None
    data: dict | None = None
    ts: datetime
