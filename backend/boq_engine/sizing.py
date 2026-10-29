"""Member sizing for RCC framed: column, beam, slab, isolated footing.

Important: these sizes exist for COSTING ONLY — never for construction.
Every output comes with a FormulaTrace so the UI can show the derivation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .geometry import ColumnGrid, FloorPlate
from .trace import FormulaTrace


@dataclass(frozen=True, slots=True)
class ColumnSize:
    b_mm: int
    d_mm: int

    @property
    def area_m2(self) -> float:
        return (self.b_mm / 1000.0) * (self.d_mm / 1000.0)


@dataclass(frozen=True, slots=True)
class BeamSize:
    width_mm: int
    depth_mm: int

    @property
    def area_m2(self) -> float:
        return (self.width_mm / 1000.0) * (self.depth_mm / 1000.0)


@dataclass(frozen=True, slots=True)
class SlabSize:
    thickness_mm: int


@dataclass(frozen=True, slots=True)
class FootingSize:
    side_m: float
    depth_mm: int
    pcc_thickness_mm: int

    @property
    def plan_area_m2(self) -> float:
        return self.side_m * self.side_m


# ------------------------------------------------------------- column size
def column_size(floors: int, rules: dict[str, Any]) -> tuple[ColumnSize, FormulaTrace]:
    """Pick a column cross-section tier based on total floors."""
    tiers = rules["sizing"]["column_tiers"]
    for tier in tiers:
        if tier["min_floors"] <= floors <= tier["max_floors"]:
            size = ColumnSize(b_mm=int(tier["b_mm"]), d_mm=int(tier["d_mm"]))
            trace = FormulaTrace(
                rule_id="sizing.column",
                version="0.1.0",
                formula="tier lookup by floors",
                inputs={
                    "floors": floors,
                    "tier_min": tier["min_floors"],
                    "tier_max": tier["max_floors"],
                },
                output=size.area_m2,
                source="rcc_framed.yaml:sizing.column_tiers",
            )
            return size, trace
    # Floors above the top tier: use the largest tier available.
    tier = tiers[-1]
    size = ColumnSize(b_mm=int(tier["b_mm"]), d_mm=int(tier["d_mm"]))
    trace = FormulaTrace(
        rule_id="sizing.column",
        version="0.1.0",
        formula="above top tier; using largest",
        inputs={"floors": floors},
        output=size.area_m2,
        source="rcc_framed.yaml:sizing.column_tiers",
    )
    return size, trace


# ------------------------------------------------------------- beam size
def beam_size(span_m: float, rules: dict[str, Any]) -> tuple[BeamSize, FormulaTrace]:
    """depth = span / divisor, rounded up to the next `rounding_mm`."""
    b = rules["sizing"]["beam"]
    raw_depth_mm = (span_m * 1000.0) / float(b["depth_divisor"])
    rounding = int(b["rounding_mm"])
    rounded = int(math.ceil(raw_depth_mm / rounding) * rounding)
    depth_mm = max(rounded, int(b["min_depth_mm"]))
    size = BeamSize(width_mm=int(b["width_mm"]), depth_mm=depth_mm)
    trace = FormulaTrace(
        rule_id="sizing.beam",
        version="0.1.0",
        formula="d = ceil(span*1000/divisor, rounding); d = max(d, min_depth)",
        inputs={
            "span_m": span_m,
            "divisor": b["depth_divisor"],
            "rounding_mm": rounding,
            "min_depth_mm": b["min_depth_mm"],
        },
        output=depth_mm,
        source="rcc_framed.yaml:sizing.beam (IS 456 Table 23)",
    )
    return size, trace


# ------------------------------------------------------------- slab size
def slab_size(span_m: float, rules: dict[str, Any]) -> tuple[SlabSize, FormulaTrace]:
    """thickness = span / divisor, bounded by [min, max], rounded up to rounding_mm."""
    s = rules["sizing"]["slab"]
    raw_mm = (span_m * 1000.0) / float(s["divisor"])
    rounding = int(s["rounding_mm"])
    rounded = int(math.ceil(raw_mm / rounding) * rounding)
    t_mm = max(int(s["min_thickness_mm"]), min(int(s["max_thickness_mm"]), rounded))
    size = SlabSize(thickness_mm=t_mm)
    trace = FormulaTrace(
        rule_id="sizing.slab",
        version="0.1.0",
        formula="t = clamp(ceil(span*1000/divisor, rounding), min_mm, max_mm)",
        inputs={
            "span_m": span_m,
            "divisor": s["divisor"],
            "rounding_mm": rounding,
            "min_mm": s["min_thickness_mm"],
            "max_mm": s["max_thickness_mm"],
        },
        output=t_mm,
        source="rcc_framed.yaml:sizing.slab",
    )
    return size, trace


# ------------------------------------------------------------- footing size
def footing_size(
    floors: int,
    plate: FloorPlate,
    grid: ColumnGrid,
    sbc_kpa: float,
    rules: dict[str, Any],
) -> tuple[FootingSize, FormulaTrace]:
    """Square isolated footing from column axial load and SBC.

    Tributary area per interior column ≈ floor_area / columns_per_floor.
    Axial load P = tributary * load_per_m2_per_floor * floors * self_weight_factor.
    Required plan area = P / SBC; side = sqrt(area), floored at min_side_m.
    """
    f = rules["sizing"]["footing"]
    tributary = plate.area_m2 / max(grid.columns_per_floor, 1)
    P_kn = (
        tributary
        * float(f["load_per_m2_per_floor_kn"])
        * floors
        * float(f["self_weight_factor"])
    )
    required_area = P_kn / sbc_kpa          # kN / kPa = m²
    side_raw = math.sqrt(required_area)
    side = max(side_raw, float(f["min_side_m"]))
    size = FootingSize(
        side_m=round(side, 2),
        depth_mm=int(f["depth_mm"]),
        pcc_thickness_mm=int(f["pcc_thickness_mm"]),
    )
    trace = FormulaTrace(
        rule_id="sizing.footing",
        version="0.1.0",
        formula="A = P/SBC; side = sqrt(A); P = trib * q * N * sw_factor",
        inputs={
            "tributary_m2": round(tributary, 3),
            "load_per_m2_per_floor_kn": f["load_per_m2_per_floor_kn"],
            "floors": floors,
            "self_weight_factor": f["self_weight_factor"],
            "sbc_kpa": sbc_kpa,
            "min_side_m": f["min_side_m"],
        },
        output=size.side_m,
        source="rcc_framed.yaml:sizing.footing",
    )
    return size, trace
