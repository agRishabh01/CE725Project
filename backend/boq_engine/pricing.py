"""Pricing: apply rates and the location cost index to a list of QuantityLines.

Rate lookup is pluggable. For Week 3, callers pass a plain dict (`rate_code → float`)
or just `None` to use each line's `fallback_rate_inr`. In Week 4 we swap this for
a DSR-backed resolver that also records the matched rate-item id in the trace.

Contingency and preliminaries are applied as percentage markups at the end.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Any

from .takeoff import QuantityLine
from .trace import FormulaTrace


# A rate resolver returns (rate, source_label). source_label is e.g. "spec_fallback"
# or "DSR 2023 §4 item 4.1.5".
RateResolver = Callable[[QuantityLine], tuple[float, str] | None]


@dataclass(frozen=True, slots=True)
class PricedLine:
    element: str
    seq: int
    description: str
    unit: str
    qty: float
    rate_code: str
    rate_inr: float
    amount_inr: float
    rate_source: str
    formula_trace: FormulaTrace | None = None
    rate_trace: FormulaTrace | None = None


@dataclass(frozen=True, slots=True)
class PricedBOQ:
    lines: list[PricedLine]
    subtotal_inr: float
    contingency_inr: float
    prelims_inr: float
    total_inr: float
    cost_index: float
    totals_by_element: dict[str, float]


# ------------------------------------------------------------- resolver factories
def dict_resolver(rate_table: dict[str, float]) -> RateResolver:
    """Resolver for a static dict (rate_code → float INR). Testing/dev."""

    def resolve(line: QuantityLine) -> tuple[float, str] | None:
        if line.rate_code in rate_table:
            return rate_table[line.rate_code], f"rate_table:{line.rate_code}"
        return None

    return resolve


def spec_fallback_resolver(line: QuantityLine) -> tuple[float, str] | None:
    """Resolver that uses the fallback rate carried on the line itself."""
    if line.fallback_rate_inr is not None:
        return float(line.fallback_rate_inr), "spec_fallback"
    return None


def chain(*resolvers: RateResolver) -> RateResolver:
    """Try resolvers left-to-right; first non-None wins."""

    def resolve(line: QuantityLine) -> tuple[float, str] | None:
        for r in resolvers:
            got = r(line)
            if got is not None:
                return got
        return None

    return resolve


# ------------------------------------------------------------- main entry point
def price_boq(
    lines: Iterable[QuantityLine],
    resolver: RateResolver | None = None,
    cost_index: float = 1.0,
    contingency_pct: float = 3.0,
    prelims_pct: float = 2.0,
) -> PricedBOQ:
    """Apply rates, cost index, and percentage markups.

    If resolver is None, uses spec_fallback_resolver so that any line with a
    fallback_rate_inr still prices. Lines with no price available end up at 0
    and their `rate_source` is marked "UNPRICED" — callers can flag these.
    """
    resolver = resolver or spec_fallback_resolver
    priced: list[PricedLine] = []
    totals_by_element: dict[str, float] = {}

    for ql in lines:
        got = resolver(ql)
        if got is None:
            rate, source = 0.0, "UNPRICED"
        else:
            raw_rate, source = got
            rate = raw_rate * cost_index
            source = f"{source} × idx={cost_index}"
        amount = round(ql.qty * rate, 2)
        rate_trace = FormulaTrace(
            rule_id="pricing.apply",
            version="0.1.0",
            formula="amount = qty * rate_base * cost_index",
            inputs={
                "qty": ql.qty,
                "rate_base_inr": round(rate / cost_index, 2) if cost_index else 0.0,
                "cost_index": cost_index,
                "rate_code": ql.rate_code,
            },
            output=amount,
            source=source,
        )
        priced.append(
            PricedLine(
                element=ql.element,
                seq=ql.seq,
                description=ql.description,
                unit=ql.unit,
                qty=ql.qty,
                rate_code=ql.rate_code,
                rate_inr=round(rate, 2),
                amount_inr=amount,
                rate_source=source,
                formula_trace=ql.trace,
                rate_trace=rate_trace,
            )
        )
        totals_by_element[ql.element] = round(
            totals_by_element.get(ql.element, 0.0) + amount, 2
        )

    subtotal = round(sum(p.amount_inr for p in priced), 2)
    contingency = round(subtotal * contingency_pct / 100.0, 2)
    prelims = round(subtotal * prelims_pct / 100.0, 2)
    total = round(subtotal + contingency + prelims, 2)

    return PricedBOQ(
        lines=priced,
        subtotal_inr=subtotal,
        contingency_inr=contingency,
        prelims_inr=prelims,
        total_inr=total,
        cost_index=cost_index,
        totals_by_element=totals_by_element,
    )


# -------------------------------------------------------------- override helper
def apply_override(line: PricedLine, qty: float | None = None, rate: float | None = None) -> PricedLine:
    """Return a new PricedLine with qty/rate overridden (immutable update).

    This exists for the API's PATCH /estimates/{id}/boq/{line_id} flow (W5).
    """
    new_qty = qty if qty is not None else line.qty
    new_rate = rate if rate is not None else line.rate_inr
    new_amount = round(new_qty * new_rate, 2)
    return replace(line, qty=new_qty, rate_inr=new_rate, amount_inr=new_amount, rate_source="override")
