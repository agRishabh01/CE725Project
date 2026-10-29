"""End-to-end orchestrator: BuildingParams dict → priced BOQ.

This is the one place that stitches together loader + takeoff + pricing. The API
and the agent orchestrator both go through this entry point so that reproducibility
holds (same inputs ⇒ same priced BOQ, byte-equal when serialised).
"""
from __future__ import annotations

from typing import Any

from .loader import load_builtin, load_builtin_spec
from .pricing import PricedBOQ, RateResolver, chain, price_boq, spec_fallback_resolver
from .takeoff import run_takeoff


def estimate_from_params(
    params: dict[str, Any],
    *,
    rate_resolver: RateResolver | None = None,
    cost_index: float = 1.0,
    contingency_pct: float = 3.0,
    prelims_pct: float = 2.0,
) -> PricedBOQ:
    """Compute a priced BOQ from a BuildingParams-like dict.

    Rule set is selected by params["structural_system"]; spec by params["spec_level"].
    If no `rate_resolver` is given, each line's spec-fallback rate is used (useful
    before the DSR is imported in W4, and as a safety net always).
    """
    rules = load_builtin(params["structural_system"])
    spec = load_builtin_spec(params.get("spec_level", "standard"))

    qlines = run_takeoff(params, rules, spec)

    resolver: RateResolver
    if rate_resolver is None:
        resolver = spec_fallback_resolver
    else:
        resolver = chain(rate_resolver, spec_fallback_resolver)

    return price_boq(
        qlines,
        resolver=resolver,
        cost_index=cost_index,
        contingency_pct=contingency_pct,
        prelims_pct=prelims_pct,
    )
