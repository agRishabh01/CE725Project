"""Estimates: create, list BOQ, patch override."""
from __future__ import annotations


def _mk_project(client) -> str:
    r = client.post("/projects", json={"name": "Hostel block A"})
    return r.json()["id"]


def _mk_estimate(client, pid: str, params: dict) -> str:
    r = client.post(
        f"/projects/{pid}/estimates",
        json={"params": params, "cost_index": 1.0},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_create_estimate_requires_params_or_brief(client, sample_params):
    pid = _mk_project(client)
    r = client.post(f"/projects/{pid}/estimates", json={})
    assert r.status_code == 422


def test_text_brief_without_params_rejected_until_w11(client):
    pid = _mk_project(client)
    r = client.post(
        f"/projects/{pid}/estimates",
        json={"text_brief": "G+4 hostel 600 m2 per floor RCC"},
    )
    assert r.status_code == 422
    assert "text brief" in r.json()["detail"].lower()


def test_create_then_fetch_estimate(client, sample_params):
    pid = _mk_project(client)
    eid = _mk_estimate(client, pid, sample_params)
    r = client.get(f"/estimates/{eid}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == eid
    assert body["status"] == "draft"


def test_boq_initially_empty_before_run(client, sample_params):
    pid = _mk_project(client)
    eid = _mk_estimate(client, pid, sample_params)
    r = client.get(f"/estimates/{eid}/boq")
    assert r.status_code == 200
    assert r.json() == []


def test_bad_params_422_with_field_path(client):
    pid = _mk_project(client)
    bad = {
        "use_type": "office",
        "plot_area_m2": 1200.0,
        "builtup_area_m2": -5.0,   # invalid
        "floors": 2,
        "floor_height_m": 3.0,
        "structural_system": "rcc_framed",
    }
    r = client.post(f"/projects/{pid}/estimates", json={"params": bad})
    assert r.status_code == 422
    body = r.json()
    assert "errors" in body
    assert any("builtup_area_m2" in e["loc"] for e in body["errors"])
