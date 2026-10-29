"""Rule-set YAML loader + Pydantic shape check."""
from __future__ import annotations

import pytest

from boq_engine.loader import load_builtin, load_rule_set


def test_rcc_framed_builtin_loads():
    rules = load_builtin("rcc_framed")
    assert rules["rule_set_id"] == "rcc_framed"
    assert rules["system"] == "rcc_framed"
    assert "sizing" in rules
    assert "geometry" in rules


def test_missing_builtin_raises():
    with pytest.raises(FileNotFoundError):
        load_builtin("martian_architecture")


def test_malformed_yaml_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("rule_set_id: x\nversion: '0.1'\n")  # missing everything else
    with pytest.raises(Exception):
        load_rule_set(bad)
