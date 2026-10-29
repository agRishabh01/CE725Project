"""Load and validate YAML rule sets.

A rule set is a plain dict (nested). We validate its *shape* with a small Pydantic
schema and keep the dict as the engine's working data structure — so new keys can
be added by an org override (FR-5) without touching Python.
"""
from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, NonNegativeInt, PositiveFloat, PositiveInt

RULES_DIR = Path(__file__).parent / "rules"
SPECS_DIR = Path(__file__).parent / "specs"


class ColumnTier(BaseModel):
    min_floors: PositiveInt
    max_floors: PositiveInt
    # 0 permitted so load-bearing masonry (no columns) can share the schema.
    b_mm: NonNegativeInt
    d_mm: NonNegativeInt


class BeamSizing(BaseModel):
    depth_divisor: PositiveFloat
    width_mm: PositiveInt
    min_depth_mm: PositiveInt
    rounding_mm: PositiveInt


class SlabSizing(BaseModel):
    divisor: PositiveFloat
    min_thickness_mm: PositiveInt
    max_thickness_mm: PositiveInt
    rounding_mm: PositiveInt


class FootingSizing(BaseModel):
    load_per_m2_per_floor_kn: PositiveFloat
    self_weight_factor: PositiveFloat
    min_side_m: PositiveFloat
    depth_mm: PositiveInt
    pcc_thickness_mm: PositiveInt


class Sizing(BaseModel):
    column_tiers: list[ColumnTier] = Field(min_length=1)
    beam: BeamSizing
    slab: SlabSizing
    footing: FootingSizing


class Geometry(BaseModel):
    default_span_m: PositiveFloat
    min_bay_m: PositiveFloat
    max_bay_m: PositiveFloat


class RuleSetSchema(BaseModel):
    """Shape check only. We keep the raw dict for engine consumption."""

    rule_set_id: str
    version: str
    system: str
    applicable_floors: list[int] = Field(min_length=2, max_length=2)
    source: str | None = None
    geometry: Geometry
    sizing: Sizing
    consumption: dict[str, dict[str, float]] | None = None


def load_rule_set(path: str | Path) -> dict[str, Any]:
    """Parse a YAML rule set, validate shape, return the raw dict."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    RuleSetSchema.model_validate(raw)  # raises on malformed
    return raw


@cache
def load_builtin(name: str) -> dict[str, Any]:
    """Load a shipped rule set by name (e.g. 'rcc_framed')."""
    path = RULES_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no built-in rule set '{name}' at {path}")
    return load_rule_set(path)


# ---------------------------------------------------------- specs (finish schedule)
class SpecSchema(BaseModel):
    """Shape check for a basic/standard/premium spec sheet. Keep lenient — raw dict wins."""

    spec_id: str
    version: str
    label: str
    flooring: dict[str, Any]
    skirting: dict[str, Any]
    dado: dict[str, Any]
    internal_plaster: dict[str, Any]
    external_plaster: dict[str, Any]
    internal_paint: dict[str, Any]
    external_paint: dict[str, Any]
    doors: dict[str, Any]
    windows: dict[str, Any]
    sanitary: dict[str, Any]
    electrical: dict[str, Any]
    waterproofing: dict[str, Any]


def load_spec(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    SpecSchema.model_validate(raw)
    return raw


@cache
def load_builtin_spec(name: str) -> dict[str, Any]:
    """Load a shipped spec sheet by name (basic|standard|premium)."""
    path = SPECS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no built-in spec '{name}' at {path}")
    return load_spec(path)
