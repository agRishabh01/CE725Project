"""Take-off: shape, coverage, and sanity on quantities."""
from __future__ import annotations

import pytest

from boq_engine.loader import load_builtin, load_builtin_spec
from boq_engine.takeoff import (
    QuantityLine,
    build_context,
    run_takeoff,
    takeoff_frame,
    takeoff_substructure,
)


EXPECTED_ELEMENTS = {
    "substructure",
    "frame",
    "masonry",
    "finishes",
    "doors_windows",
    "waterproofing",
    "services",
    "external_works",
    "miscellaneous",
}


@pytest.fixture
def params_g4_hostel_std():
    return {
        "use_type": "hostel",
        "plot_area_m2": 1800.0,
        "builtup_area_m2": 3000.0,
        "floors": 5,  # G+4
        "floor_height_m": 3.0,
        "aspect_ratio": 1.5,
        "structural_system": "rcc_framed",
        "spec_level": "standard",
        "sbc_kpa": 150.0,
        "plan_shape": "rectangular",
        "location": "Mumbai",
        "source": "form",
    }


@pytest.fixture
def rules():
    return load_builtin("rcc_framed")


@pytest.fixture
def spec_std():
    return load_builtin_spec("standard")


def test_run_takeoff_covers_all_nine_elements(params_g4_hostel_std, rules, spec_std):
    lines = run_takeoff(params_g4_hostel_std, rules, spec_std)
    seen = {ln.element for ln in lines}
    assert seen == EXPECTED_ELEMENTS, f"missing: {EXPECTED_ELEMENTS - seen}, extra: {seen - EXPECTED_ELEMENTS}"


def test_run_takeoff_produces_target_line_count(params_g4_hostel_std, rules, spec_std):
    lines = run_takeoff(params_g4_hostel_std, rules, spec_std)
    # Plan says ~40-80 items; floors>=4 pulls in the lift as a bonus line → ~50.
    assert 45 <= len(lines) <= 70, f"expected 45-70, got {len(lines)}"


def test_every_line_carries_a_formula_trace(params_g4_hostel_std, rules, spec_std):
    lines = run_takeoff(params_g4_hostel_std, rules, spec_std)
    for ln in lines:
        assert ln.trace is not None
        assert ln.trace.rule_id.startswith("takeoff.")
        assert ln.trace.formula
        assert isinstance(ln.trace.inputs, dict)


def test_substructure_quantities_scale_with_floors(rules, spec_std):
    base = {
        "use_type": "residential",
        "plot_area_m2": 900.0,
        "builtup_area_m2": 500.0,
        "floors": 2,
        "floor_height_m": 3.0,
        "aspect_ratio": 1.3,
        "structural_system": "rcc_framed",
        "spec_level": "standard",
        "sbc_kpa": 150.0,
    }
    s_small = takeoff_substructure(build_context(base, rules, spec_std))
    s_big = takeoff_substructure(build_context({**base, "floors": 6, "builtup_area_m2": 1500.0}, rules, spec_std))
    # Taller building ⇒ bigger footings ⇒ more RCC in substructure (seq 3).
    rcc_small = next(x.qty for x in s_small if x.seq == 3)
    rcc_big = next(x.qty for x in s_big if x.seq == 3)
    assert rcc_big > rcc_small


def test_frame_rcc_scales_with_floors(rules, spec_std):
    base = {
        "use_type": "office",
        "plot_area_m2": 1200.0,
        "builtup_area_m2": 1800.0,
        "floors": 3,
        "floor_height_m": 3.0,
        "aspect_ratio": 1.5,
        "structural_system": "rcc_framed",
        "spec_level": "standard",
        "sbc_kpa": 180.0,
    }
    small = takeoff_frame(build_context(base, rules, spec_std))
    big = takeoff_frame(build_context({**base, "floors": 6, "builtup_area_m2": 3600.0}, rules, spec_std))
    col_small = next(x.qty for x in small if x.seq == 1)
    col_big = next(x.qty for x in big if x.seq == 1)
    assert col_big > col_small * 1.5  # doubling floors + area roughly doubles columns at least


def test_lift_line_only_when_floors_ge_4(rules, spec_std):
    base_short = {
        "use_type": "residential", "plot_area_m2": 800.0, "builtup_area_m2": 400.0,
        "floors": 2, "floor_height_m": 3.0, "aspect_ratio": 1.3,
        "structural_system": "rcc_framed", "spec_level": "standard", "sbc_kpa": 150.0,
    }
    short = run_takeoff(base_short, rules, spec_std)
    tall = run_takeoff({**base_short, "floors": 5, "builtup_area_m2": 1500.0}, rules, spec_std)
    assert not any("Passenger lift" in ln.description for ln in short)
    assert any("Passenger lift" in ln.description for ln in tall)


def test_takeoff_runs_for_all_three_structural_systems(spec_std):
    base = {
        "use_type": "residential", "plot_area_m2": 400.0, "builtup_area_m2": 800.0,
        "floors": 2, "floor_height_m": 3.0, "aspect_ratio": 1.2,
        "spec_level": "standard", "sbc_kpa": 150.0,
    }
    for system in ("rcc_framed", "rcc_flat_slab", "load_bearing"):
        rs = load_builtin(system)
        lines = run_takeoff({**base, "structural_system": system}, rs, spec_std)
        assert len(lines) >= 30, f"too few lines for {system}: {len(lines)}"
        assert all(isinstance(ln, QuantityLine) for ln in lines)
