"""Geometry: floor plate dimensions and column grid."""
from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from boq_engine.geometry import column_grid, floor_plate
from boq_engine.loader import load_builtin


@pytest.fixture(scope="module")
def rules():
    return load_builtin("rcc_framed")


def test_floor_plate_square_at_ratio_1(rules):
    plate, trace = floor_plate(builtup_area_m2=400.0, floors=1, aspect_ratio=1.0)
    assert math.isclose(plate.length_m, 20.0, rel_tol=1e-6)
    assert math.isclose(plate.breadth_m, 20.0, rel_tol=1e-6)
    assert math.isclose(plate.area_m2, 400.0, rel_tol=1e-6)
    assert math.isclose(plate.perimeter_m, 80.0, rel_tol=1e-6)
    assert trace.rule_id == "geometry.floor_plate"


def test_floor_plate_rectangular(rules):
    # 1200 m² per floor at aspect 1.5 ⇒ L*B = 1200, L/B = 1.5
    # L = sqrt(1200*1.5) ≈ 42.426, B = sqrt(1200/1.5) ≈ 28.284
    plate, _ = floor_plate(builtup_area_m2=2400.0, floors=2, aspect_ratio=1.5)
    assert math.isclose(plate.length_m, math.sqrt(1800), rel_tol=1e-6)
    assert math.isclose(plate.breadth_m, math.sqrt(800), rel_tol=1e-6)
    assert math.isclose(plate.length_m / plate.breadth_m, 1.5, rel_tol=1e-6)


def test_column_grid_rect_building(rules):
    plate, _ = floor_plate(builtup_area_m2=600.0, floors=1, aspect_ratio=1.5)
    # L≈30, B≈20. Target span 4m ⇒ bays L=7 or 8, B=5
    grid, trace = column_grid(plate, rules)
    assert grid.bays_long >= 1 and grid.bays_short >= 1
    g = rules["geometry"]
    assert g["min_bay_m"] <= grid.span_long_m <= g["max_bay_m"]
    assert g["min_bay_m"] <= grid.span_short_m <= g["max_bay_m"]
    assert grid.columns_per_floor == (grid.bays_long + 1) * (grid.bays_short + 1)
    assert trace.rule_id == "geometry.column_grid"


@given(
    area=st.floats(min_value=50.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
    floors=st.integers(min_value=1, max_value=10),
    ratio=st.floats(min_value=0.4, max_value=3.5, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100, deadline=None)
def test_floor_plate_invariants(area, floors, ratio):
    plate, _ = floor_plate(builtup_area_m2=area, floors=floors, aspect_ratio=ratio)
    # Area equals L*B regardless of ratio.
    assert math.isclose(plate.length_m * plate.breadth_m, area / floors, rel_tol=1e-9)
    assert plate.length_m > 0 and plate.breadth_m > 0


@given(
    area=st.floats(min_value=200.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
    ratio=st.floats(min_value=0.7, max_value=2.5, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50, deadline=None)
def test_column_grid_bay_bounds(area, ratio):
    rules = load_builtin("rcc_framed")
    plate, _ = floor_plate(builtup_area_m2=area, floors=1, aspect_ratio=ratio)
    grid, _ = column_grid(plate, rules)
    # If the plate is physically bigger than max_bay in either axis, each actual bay
    # must land inside [min_bay, max_bay].
    g = rules["geometry"]
    if plate.length_m >= g["min_bay_m"]:
        assert grid.span_long_m <= g["max_bay_m"] * 1.01
    if plate.breadth_m >= g["min_bay_m"]:
        assert grid.span_short_m <= g["max_bay_m"] * 1.01
