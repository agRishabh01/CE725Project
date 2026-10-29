"""Pricing: rate resolvers, cost index, percentage markups, override."""
from __future__ import annotations

import pytest

from boq_engine.estimate import estimate_from_params
from boq_engine.pricing import (
    apply_override,
    chain,
    dict_resolver,
    price_boq,
    spec_fallback_resolver,
)
from boq_engine.takeoff import QuantityLine
from boq_engine.trace import FormulaTrace


def _line(code: str, qty: float, fallback: float | None, seq: int = 1) -> QuantityLine:
    return QuantityLine(
        element="test",
        seq=seq,
        description="test line",
        unit="m3",
        qty=qty,
        rate_code=code,
        fallback_rate_inr=fallback,
        trace=FormulaTrace(
            rule_id="test.x", version="0.0", formula="qty",
            inputs={}, output=qty, source=None,
        ),
    )


# ------------------------------------------------------------- resolvers
def test_dict_resolver_hits_known_code():
    r = dict_resolver({"RCC": 8500.0})
    rate, source = r(_line("RCC", 1.0, None))
    assert rate == 8500.0
    assert "RCC" in source


def test_dict_resolver_misses_unknown_code():
    r = dict_resolver({"RCC": 8500.0})
    assert r(_line("STEEL", 1.0, None)) is None


def test_spec_fallback_resolver_uses_line_rate():
    rate, source = spec_fallback_resolver(_line("PLASTER_INT", 10.0, 290.0))
    assert rate == 290.0
    assert source == "spec_fallback"


def test_chain_prefers_first():
    primary = dict_resolver({"RCC": 10000.0})
    chained = chain(primary, spec_fallback_resolver)
    rate, _ = chained(_line("RCC", 1.0, 5000.0))  # spec says 5000, dict says 10000
    assert rate == 10000.0


def test_chain_falls_through():
    primary = dict_resolver({"STEEL": 85.0})
    chained = chain(primary, spec_fallback_resolver)
    rate, src = chained(_line("UNKNOWN", 1.0, 420.0))
    assert rate == 420.0
    assert "fallback" in src


# ------------------------------------------------------------- price_boq
def test_price_boq_applies_cost_index():
    lines = [_line("A", 100.0, 50.0)]
    p = price_boq(lines, cost_index=1.2, contingency_pct=0, prelims_pct=0)
    assert p.lines[0].rate_inr == pytest.approx(60.0)
    assert p.lines[0].amount_inr == pytest.approx(6000.0)
    assert p.subtotal_inr == pytest.approx(6000.0)


def test_price_boq_percentage_markups():
    lines = [_line("A", 1.0, 100.0)]
    p = price_boq(lines, cost_index=1.0, contingency_pct=3, prelims_pct=2)
    assert p.subtotal_inr == 100.0
    assert p.contingency_inr == pytest.approx(3.0)
    assert p.prelims_inr == pytest.approx(2.0)
    assert p.total_inr == pytest.approx(105.0)


def test_unpriced_line_marked_zero_not_crash():
    lines = [_line("MYSTERY", 10.0, None)]
    p = price_boq(lines, resolver=lambda _: None, contingency_pct=0, prelims_pct=0)
    assert p.lines[0].amount_inr == 0.0
    assert p.lines[0].rate_source == "UNPRICED"


def test_totals_by_element_accumulate():
    lines = [
        QuantityLine("substructure", 1, "a", "m3", 1.0, "A", 100.0, None),
        QuantityLine("substructure", 2, "b", "m3", 2.0, "B", 100.0, None),
        QuantityLine("frame",        1, "c", "m3", 3.0, "C", 100.0, None),
    ]
    p = price_boq(lines, contingency_pct=0, prelims_pct=0)
    assert p.totals_by_element["substructure"] == pytest.approx(300.0)
    assert p.totals_by_element["frame"] == pytest.approx(300.0)


# ------------------------------------------------------------- override
def test_apply_override_recomputes_amount():
    lines = [_line("A", 10.0, 100.0)]
    priced = price_boq(lines, contingency_pct=0, prelims_pct=0).lines[0]
    bumped = apply_override(priced, qty=20.0)
    assert bumped.qty == 20.0
    assert bumped.amount_inr == pytest.approx(2000.0)
    assert bumped.rate_source == "override"


# ------------------------------------------------------------- end-to-end
def test_estimate_from_params_runs_e2e():
    params = {
        "use_type": "hostel",
        "plot_area_m2": 1800.0,
        "builtup_area_m2": 3000.0,
        "floors": 5,
        "floor_height_m": 3.0,
        "aspect_ratio": 1.5,
        "structural_system": "rcc_framed",
        "spec_level": "standard",
        "sbc_kpa": 150.0,
    }
    priced = estimate_from_params(params)
    # Core "done when" from the Week 3 plan.
    assert 45 <= len(priced.lines) <= 70
    assert priced.total_inr > 0
    for ln in priced.lines:
        assert ln.formula_trace is not None
        assert ln.rate_trace is not None
    # All 9 elements accounted for in totals_by_element.
    assert len(priced.totals_by_element) == 9


def test_estimate_reproducibility():
    """Same inputs ⇒ byte-equal line-level amounts across runs (PDR reproducibility)."""
    params = {
        "use_type": "office",
        "plot_area_m2": 1200.0,
        "builtup_area_m2": 2400.0,
        "floors": 4,
        "floor_height_m": 3.2,
        "aspect_ratio": 1.4,
        "structural_system": "rcc_framed",
        "spec_level": "standard",
        "sbc_kpa": 180.0,
    }
    a = estimate_from_params(params)
    b = estimate_from_params(params)
    assert a.total_inr == b.total_inr
    assert [ln.amount_inr for ln in a.lines] == [ln.amount_inr for ln in b.lines]


def test_premium_spec_is_more_expensive_than_basic():
    base = {
        "use_type": "residential",
        "plot_area_m2": 600.0,
        "builtup_area_m2": 1200.0,
        "floors": 3,
        "floor_height_m": 3.0,
        "aspect_ratio": 1.4,
        "structural_system": "rcc_framed",
        "sbc_kpa": 150.0,
    }
    cheap = estimate_from_params({**base, "spec_level": "basic"})
    fancy = estimate_from_params({**base, "spec_level": "premium"})
    assert fancy.total_inr > cheap.total_inr * 1.3
