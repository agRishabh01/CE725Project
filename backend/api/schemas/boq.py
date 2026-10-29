"""BOQ, estimate, and formula-trace schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Element = Literal[
    "substructure",
    "frame",
    "masonry",
    "finishes",
    "doors_windows",
    "waterproofing",
    "services",
    "external_works",
    "miscellaneous",
]

EstimateStatus = Literal["draft", "in_review", "approved"]


class FormulaTrace(BaseModel):
    """Why a quantity has the value it has. Mirrors boq_engine.trace.FormulaTrace."""

    rule_id: str
    version: str
    formula: str
    inputs: dict[str, float | int | str]
    output: float
    source: str | None = None  # textbook/IS-code reference


class BOQLineBase(BaseModel):
    element: Element
    seq: int = Field(ge=1)
    description: str
    unit: str
    qty: float = Field(ge=0)
    rate: float | None = None
    amount: float | None = None
    rate_item_id: str | None = None
    formula_trace: FormulaTrace | None = None
    override_reason: str | None = None
    is_overridden: bool = False


class BOQLineOut(BOQLineBase):
    id: str
    estimate_id: str


class BOQLinePatch(BaseModel):
    """Payload for PATCH /estimates/{id}/boq/{line_id}."""

    qty: float | None = Field(default=None, ge=0)
    rate: float | None = Field(default=None, ge=0)
    override_reason: str = Field(min_length=3, max_length=500)


class EstimateTotals(BaseModel):
    total_cost: float
    by_element: dict[Element, float]
    cost_per_m2: float
    concrete_m3_per_m2: float | None = None
    steel_kg_per_m2: float | None = None


class EstimateOut(BaseModel):
    id: str
    project_id: str
    version: int
    status: EstimateStatus
    rule_set_id: str | None
    rate_edition_id: str | None
    cost_index: float
    total_cost: float | None
    totals_by_element: dict | None
    scenario_label: str | None
    created_at: datetime
