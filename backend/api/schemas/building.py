"""BuildingParams schema — the input to the engine, source of truth for a run.

Fields match the PDR §Project intake wizard (FR-1).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

UseType = Literal[
    "residential", "hostel", "office", "institutional", "commercial", "mixed_use"
]
StructuralSystem = Literal["rcc_framed", "rcc_flat_slab", "load_bearing"]
SpecLevel = Literal["basic", "standard", "premium"]
PlanShape = Literal["rectangular", "l_shape", "square", "irregular"]
InputSource = Literal["form", "text", "plan"]


class BuildingParams(BaseModel):
    """Validated building parameters. All quantities metric."""

    use_type: UseType
    plot_area_m2: float = Field(gt=0, le=100_000)
    builtup_area_m2: float = Field(gt=0, le=200_000)
    floors: int = Field(ge=1, le=20)
    floor_height_m: float = Field(ge=2.4, le=6.0)
    plan_shape: PlanShape = "rectangular"
    aspect_ratio: float = Field(default=1.5, gt=0.3, lt=4.0)
    structural_system: StructuralSystem
    spec_level: SpecLevel = "standard"
    sbc_kpa: float = Field(default=150.0, ge=50.0, le=600.0)
    location: str = "Delhi"
    source: InputSource = "form"

    @model_validator(mode="after")
    def _builtup_vs_plot(self) -> BuildingParams:
        cap = self.plot_area_m2 * self.floors * 1.1
        if self.builtup_area_m2 > cap:
            raise ValueError(
                f"builtup_area_m2 ({self.builtup_area_m2}) exceeds plot_area * floors * 1.1 ({cap:.1f})"
            )
        return self


class FieldConfidence(BaseModel):
    """Per-field confidence attached when BuildingParams came from an agent."""

    field: str
    confidence: float = Field(ge=0.0, le=1.0)
    source_snippet: str | None = None


class BuildingParamsWithConfidence(BaseModel):
    params: BuildingParams
    confidences: list[FieldConfidence] = Field(default_factory=list)
    source: InputSource = "text"
