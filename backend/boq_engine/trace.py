"""FormulaTrace: the breadcrumb attached to every quantity the engine computes.

A trace answers four questions for the user who clicks a BOQ cell:
  1. Which rule produced this?         rule_id, version
  2. What's the formula?                formula (as a readable string)
  3. What inputs went in?               inputs dict
  4. What came out?                     output
Plus optional source attribution (textbook/IS-code reference).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True, slots=True)
class FormulaTrace:
    rule_id: str
    version: str
    formula: str
    inputs: dict[str, float | int | str]
    output: float
    source: str | None = None
    children: tuple[FormulaTrace, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["children"] = [c if isinstance(c, dict) else asdict(c) for c in self.children]
        return d
