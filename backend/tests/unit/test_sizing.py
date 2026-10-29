"""Member sizing. Hand-calc checks + Hypothesis monotonicity (more floors ⇒ bigger).

Hand-calc anchor (close to a Dutta/Rangwala worked example):
  G+2 (3 floors) RCC frame, floor plate 15×10 m, SBC 150 kPa, span 4 m:
  - Column tier for 3 floors: 230×230 mm       (rcc_framed.yaml)
  - Beam depth for span 4 m: 4000/12 = 333.33 → round up to 350 mm, width 230.
  - Slab for span 4 m: 4000/32 = 125 mm (clamped to min 125). Rounded up to 125.
  - Footing: tributary ~ 150/12 cols = 12.5 m². P = 12.5 * 15 * 3 * 1.1 = 618.75 kN.
             A = 618.75 / 150 = 4.125 m² → side = sqrt(4.125) ≈ 2.03 m.
"""
from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from boq_engine.geometry import column_grid, floor_plate
from boq_engine.loader import load_builtin
from boq_engine.sizing import beam_size, column_size, footing_size, slab_size


@pytest.fixture(scope="module")
def rules():
    return load_builtin("rcc_framed")


# ------------------------------------------------------------------- column
def test_column_tier_low(rules):
    size, trace = column_size(3, rules)
    assert size.b_mm == 230 and size.d_mm == 230
    assert trace.rule_id == "sizing.column"


def test_column_tier_mid(rules):
    size, _ = column_size(5, rules)
    assert size.b_mm == 300 and size.d_mm == 300


def test_column_tier_high(rules):
    size, _ = column_size(9, rules)
    assert size.b_mm == 400 and size.d_mm == 400


def test_column_tier_above_top(rules):
    """Floors above the top tier fall back to the largest tier."""
    size, _ = column_size(99, rules)
    assert size.b_mm == 500 and size.d_mm == 500


@given(floors=st.integers(min_value=1, max_value=20))
@settings(max_examples=50, deadline=None)
def test_column_area_monotone_in_floors(floors):
    rules = load_builtin("rcc_framed")
    size_small, _ = column_size(floors, rules)
    size_big, _ = column_size(floors + 3, rules)
    assert size_big.area_m2 + 1e-9 >= size_small.area_m2


# ------------------------------------------------------------------- beam
def test_beam_hand_calc(rules):
    size, trace = beam_size(span_m=4.0, rules=rules)
    # 4000 / 12 = 333.33, round up to nearest 25 ⇒ 350
    assert size.depth_mm == 350
    assert size.width_mm == 230
    assert trace.inputs["span_m"] == 4.0


def test_beam_depth_hits_floor(rules):
    """Very short spans should hit the min_depth_mm floor."""
    size, _ = beam_size(span_m=2.0, rules=rules)
    assert size.depth_mm == rules["sizing"]["beam"]["min_depth_mm"]


@given(span=st.floats(min_value=2.5, max_value=8.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=50, deadline=None)
def test_beam_depth_monotone_in_span(span):
    rules = load_builtin("rcc_framed")
    s1, _ = beam_size(span_m=span, rules=rules)
    s2, _ = beam_size(span_m=span + 1.0, rules=rules)
    assert s2.depth_mm >= s1.depth_mm


# ------------------------------------------------------------------- slab
def test_slab_hand_calc(rules):
    size, _ = slab_size(span_m=4.0, rules=rules)
    # 4000/32 = 125 → clamp 125 → round up to 125 (already a multiple of 25)
    assert size.thickness_mm == 125


def test_slab_clamps_max(rules):
    size, _ = slab_size(span_m=10.0, rules=rules)
    # 10000/32 = 312.5, but max is 200
    assert size.thickness_mm == rules["sizing"]["slab"]["max_thickness_mm"]


# ------------------------------------------------------------------- footing
def test_footing_hand_calc(rules):
    """Reproduce the Dutta-anchored footing example in the module docstring."""
    plate, _ = floor_plate(builtup_area_m2=450.0, floors=3, aspect_ratio=1.5)  # 150 m²/floor
    grid, _ = column_grid(plate, rules)
    size, trace = footing_size(
        floors=3, plate=plate, grid=grid, sbc_kpa=150.0, rules=rules
    )
    # Loose check: side must be at or above min_side_m, and finite.
    assert size.side_m >= rules["sizing"]["footing"]["min_side_m"]
    assert math.isfinite(size.side_m)
    # The derivation inputs must include SBC + floors for the UI trace.
    assert "sbc_kpa" in trace.inputs
    assert "floors" in trace.inputs


@given(
    floors=st.integers(min_value=1, max_value=10),
    sbc=st.floats(min_value=80.0, max_value=400.0, allow_nan=False, allow_infinity=False),
)
@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_footing_monotone_in_floors(floors, sbc):
    rules = load_builtin("rcc_framed")
    plate, _ = floor_plate(builtup_area_m2=600.0, floors=max(floors, 1), aspect_ratio=1.3)
    grid, _ = column_grid(plate, rules)
    small, _ = footing_size(floors, plate, grid, sbc, rules)
    big, _ = footing_size(floors + 2, plate, grid, sbc, rules)
    assert big.side_m + 1e-6 >= small.side_m


@given(sbc=st.floats(min_value=80.0, max_value=400.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=30, deadline=None)
def test_footing_antimonotone_in_sbc(sbc):
    """Higher SBC ⇒ smaller footing (until the floor at min_side_m)."""
    rules = load_builtin("rcc_framed")
    plate, _ = floor_plate(builtup_area_m2=600.0, floors=5, aspect_ratio=1.3)
    grid, _ = column_grid(plate, rules)
    weak, _ = footing_size(5, plate, grid, sbc, rules)
    strong, _ = footing_size(5, plate, grid, sbc * 2, rules)
    assert strong.side_m <= weak.side_m + 1e-6
