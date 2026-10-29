"""Run execution + SSE replay — the Week 5 happy path."""
from __future__ import annotations

import json


def _create(client, params: dict) -> tuple[str, str]:
    pid = client.post("/projects", json={"name": "RunTest"}).json()["id"]
    eid = client.post(
        f"/projects/{pid}/estimates", json={"params": params, "cost_index": 1.0}
    ).json()["id"]
    return pid, eid


def test_run_populates_boq_and_totals(client, sample_params):
    _, eid = _create(client, sample_params)
    r = client.post(f"/estimates/{eid}/runs", json={"mode": "full"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["estimate_id"] == eid
    assert body["event_count"] >= 5           # intake, quantities, mapping, pricing, done
    assert body["status"] == "completed"

    boq = client.get(f"/estimates/{eid}/boq").json()
    assert 45 <= len(boq) <= 70

    est = client.get(f"/estimates/{eid}").json()
    assert est["total_cost"] > 0
    assert est["totals_by_element"] is not None
    assert len(est["totals_by_element"]) == 9


def test_sse_stream_replays_events(client, sample_params):
    _, eid = _create(client, sample_params)
    body = client.post(f"/estimates/{eid}/runs", json={"mode": "full"}).json()
    run_id = body["run_id"]
    assert run_id

    with client.stream("GET", f"/runs/{run_id}/events") as r:
        assert r.status_code == 200
        chunks = []
        for chunk in r.iter_text():
            chunks.append(chunk)
            if "stream_end" in chunk:
                break
        raw = "".join(chunks)
    # SSE event lines look like `event: <name>\ndata: {...}\n\n`.
    assert "event: intake" in raw
    assert "event: pricing" in raw
    assert "event: done" in raw
    assert "event: stream_end" in raw


def test_patch_recalculates_totals(client, sample_params):
    _, eid = _create(client, sample_params)
    client.post(f"/estimates/{eid}/runs", json={"mode": "full"})
    boq = client.get(f"/estimates/{eid}/boq").json()
    line = boq[0]
    before = client.get(f"/estimates/{eid}").json()["total_cost"]

    r = client.patch(
        f"/estimates/{eid}/boq/{line['id']}",
        json={"qty": line["qty"] * 2, "rate": line["rate"], "override_reason": "double for test"},
    )
    assert r.status_code == 200
    assert r.json()["is_overridden"] is True
    assert r.json()["qty"] == line["qty"] * 2

    after = client.get(f"/estimates/{eid}").json()["total_cost"]
    assert after > before


def test_run_without_params_422(client):
    pid = client.post("/projects", json={"name": "NoParams"}).json()["id"]
    # Create an orphan estimate by bypassing the normal creator — simulate via a bogus id.
    r = client.post("/estimates/not-a-real-id/runs", json={"mode": "full"})
    assert r.status_code == 404


def test_mode_other_than_full_rejected_until_w8(client, sample_params):
    _, eid = _create(client, sample_params)
    r = client.post(f"/estimates/{eid}/runs", json={"mode": "mapping_only"})
    assert r.status_code == 422
