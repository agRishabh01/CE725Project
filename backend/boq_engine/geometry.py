"""Floor-plate geometry: dimensions and column grid.

Inputs come from BuildingParams (API schema). Outputs feed sizing.py and takeoff.py.
Every public function returns a value AND a FormulaTrace so the UI can show its work.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .trace import FormulaTrace


@dataclass(frozen=True, slots=True)
class FloorPlate:
    length_m: float
    breadth_m: float
    area_m2: float          # length * breadth (one floor)
    perimeter_m: float


@dataclass(frozen=True, slots=True)
class ColumnGrid:
    bays_long: int          # bays along L (so columns_long = bays_long + 1)
    bays_short: int         # bays along B
    span_long_m: float      # actual bay dimension along L (not the target span)
    span_short_m: float
    columns_per_floor: int


# ---------------------------------------------------------------- floor plate
def floor_plate(
    builtup_area_m2: float,
    floors: int,
    aspect_ratio: float,
) -> tuple[FloorPlate, FormulaTrace]:
    """Rectangular floor plate from built-up area and aspect ratio L/B.

    builtup_area / floors ≈ one floor's gross area.
    L = sqrt(area * ratio);  B = sqrt(area / ratio).
    """
    area = builtup_area_m2 / floors
    L = math.sqrt(area * aspect_ratio)
    B = math.sqrt(area / aspect_ratio)
    perim = 2 * (L + B)
    plate = FloorPlate(length_m=L, breadth_m=B, area_m2=area, perimeter_m=perim)
    trace = FormulaTrace(
        rule_id="geometry.floor_plate",
        version="0.1.0",
        formula="L=sqrt(A*r), B=sqrt(A/r), A=builtup/floors",
        inputs={
            "builtup_area_m2": builtup_area_m2,
            "floors": floors,
            "aspect_ratio": aspect_ratio,
        },
        output=area,
        source="geometric identity",
    )
    return plate, trace


# ---------------------------------------------------------------- column grid
def column_grid(
    plate: FloorPlate,
    rules: dict[str, Any],
) -> tuple[ColumnGrid, FormulaTrace]:
    """Lay columns on a near-uniform grid respecting min/max bay from the rule set.

    Target span is `rules.geometry.default_span_m`. We pick the integer number
    of bays that keeps actual spans inside [min_bay_m, max_bay_m] and nearest
    to the target. Columns per floor = (bays_long+1) * (bays_short+1).
    """
    g = rules["geometry"]
    target = g["default_span_m"]
    min_bay = g["min_bay_m"]
    max_bay = g["max_bay_m"]

    bays_L = _choose_bays(plate.length_m, target, min_bay, max_bay)
    bays_B = _choose_bays(plate.breadth_m, target, min_bay, max_bay)
    span_L = plate.length_m / bays_L
    span_B = plate.breadth_m / bays_B
    cols = (bays_L + 1) * (bays_B + 1)
    grid = ColumnGrid(
        bays_long=bays_L,
        bays_short=bays_B,
        span_long_m=span_L,
        span_short_m=span_B,
        columns_per_floor=cols,
    )
    trace = FormulaTrace(
        rule_id="geometry.column_grid",
        version="0.1.0",
        formula="n = (L/s + 1) * (B/s + 1); bays chosen so min_bay <= actual <= max_bay",
        inputs={
            "L_m": plate.length_m,
            "B_m": plate.breadth_m,
            "target_span_m": target,
            "min_bay_m": min_bay,
            "max_bay_m": max_bay,
        },
        output=cols,
        source="rcc_framed.yaml:geometry",
    )
    return grid, trace


def _choose_bays(side_m: float, target_m: float, min_m: float, max_m: float) -> int:
    """Pick an integer bay count whose actual bay sits in [min_m, max_m] and is nearest target."""
    # Natural guess: round(side/target). Floor and ceil are both candidates when
    # neither cleanly divides. Pick whichever yields an actual bay nearest target
    # while staying inside the min/max window; if nothing fits, use whichever
    # keeps us closest to the window.
    guess = max(1, round(side_m / target_m))
    candidates = {max(1, guess - 1), guess, guess + 1}
    valid = [b for b in candidates if min_m <= side_m / b <= max_m]
    pool = valid if valid else list(candidates)
    return min(pool, key=lambda b: abs(side_m / b - target_m))
