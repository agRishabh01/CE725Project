"""Gate 1 reproducibility test.

Each case is frozen as a JSON snapshot of the priced BOQ. The test asserts that
the current engine, when run on the same inputs, produces byte-equal line amounts
and byte-equal totals. If snapshots are missing, the test writes them (first run);
if they're stale, it fails loudly — the engineer either re-runs with the env var
to regenerate, or fixes the regression.

Regenerate with: `UPDATE_GOLDEN=1 pytest tests/golden/ -q`
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from boq_engine.estimate import estimate_from_params

from .cases import GOLDEN_CASES

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
SNAPSHOT_DIR.mkdir(exist_ok=True)


def _snapshot(name: str, params: dict) -> dict:
    priced = estimate_from_params(params)
    return {
        "params": params,
        "line_count": len(priced.lines),
        "subtotal_inr": priced.subtotal_inr,
        "contingency_inr": priced.contingency_inr,
        "prelims_inr": priced.prelims_inr,
        "total_inr": priced.total_inr,
        "totals_by_element": priced.totals_by_element,
        "lines": [
            {
                "element": ln.element, "seq": ln.seq, "unit": ln.unit,
                "qty": ln.qty, "rate_inr": ln.rate_inr, "amount_inr": ln.amount_inr,
                "rate_code": ln.rate_code,
            }
            for ln in priced.lines
        ],
    }


@pytest.mark.parametrize("name", list(GOLDEN_CASES))
def test_engine_matches_golden_snapshot(name):
    path = SNAPSHOT_DIR / f"{name}.json"
    current = _snapshot(name, GOLDEN_CASES[name])

    update = os.getenv("UPDATE_GOLDEN") == "1"
    if update or not path.exists():
        path.write_text(json.dumps(current, indent=2, sort_keys=True), encoding="utf-8")
        pytest.skip(f"wrote fresh snapshot: {path.name}")
        return

    frozen = json.loads(path.read_text(encoding="utf-8"))

    # Scalar totals must match to the paisa.
    assert current["line_count"] == frozen["line_count"], (
        f"line count drift: got {current['line_count']}, expected {frozen['line_count']}"
    )
    assert current["total_inr"] == frozen["total_inr"], (
        f"TOTAL drift: got {current['total_inr']}, expected {frozen['total_inr']}"
    )
    assert current["totals_by_element"] == frozen["totals_by_element"]

    # Every line amount matches byte-for-byte.
    cur_lines = {(l["element"], l["seq"]): l for l in current["lines"]}
    frz_lines = {(l["element"], l["seq"]): l for l in frozen["lines"]}
    assert set(cur_lines) == set(frz_lines), (
        f"line-key set changed: added={set(cur_lines)-set(frz_lines)}, "
        f"removed={set(frz_lines)-set(cur_lines)}"
    )
    for key, cur in cur_lines.items():
        frz = frz_lines[key]
        for field in ("qty", "rate_inr", "amount_inr", "unit", "rate_code"):
            assert cur[field] == frz[field], (
                f"{key} drift on {field}: {cur[field]} != {frz[field]}"
            )
