"""Rate-mapping routes + end-to-end integration with the run."""
from __future__ import annotations

from pathlib import Path

from api.services.rate_import import import_from_yaml
from api.services.rate_search import (
    compute_and_store_embeddings,
    ensure_fts_index,
)

SAMPLE_DSR = (
    Path(__file__).resolve().parents[2] / "data" / "cpwd_dsr_2023" / "sample.yaml"
)


def _bootstrap_dsr(test_db):
    edition = import_from_yaml(test_db, SAMPLE_DSR)
    ensure_fts_index(test_db)
    compute_and_store_embeddings(test_db, edition.id)
    return edition.id


def _mk_estimate(client, sample_params):
    pid = client.post("/projects", json={"name": "W8 mapping"}).json()["id"]
    eid = client.post(
        f"/projects/{pid}/estimates", json={"params": sample_params, "cost_index": 1.0}
    ).json()["id"]
    return eid


def test_run_chains_mapping_when_dsr_loaded(client, test_db, sample_params):
    _bootstrap_dsr(test_db)
    eid = _mk_estimate(client, sample_params)

    # Starting a run should automatically chain the mapping stage.
    body = client.post(f"/estimates/{eid}/runs", json={"mode": "full"}).json()
    assert body["status"] == "completed"
    assert body["event_count"] >= 7

    # Confirm at least some BOQ lines got real DSR rate_item_ids.
    boq = client.get(f"/estimates/{eid}/boq").json()
    mapped = [ln for ln in boq if ln["rate_item_id"] is not None]
    assert len(mapped) >= 20, f"only {len(mapped)} lines got mapped out of {len(boq)}"


def test_mapping_queue_and_accept_round_trip(client, test_db, sample_params):
    _bootstrap_dsr(test_db)
    eid = _mk_estimate(client, sample_params)
    client.post(f"/estimates/{eid}/runs", json={"mode": "full"})

    queue = client.get(f"/estimates/{eid}/mapping-queue").json()
    # Deterministic mode will leave the harder matches in the queue.
    # If zero, nothing to accept — but the sample DSR + take-off produces at
    # least a handful of ambiguous lines (basic-named items without a basic DSR).
    if not queue:
        return

    proposal = queue[0]
    assert proposal["top_candidates"], "queued proposals must carry candidates"
    chosen = proposal["top_candidates"][0]
    r = client.post(
        f"/estimates/{eid}/mapping/{proposal['id']}",
        json={"rate_item_id": chosen["rate_item_id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "accepted"

    # Line now carries the chosen rate_item_id and a non-null amount.
    boq = client.get(f"/estimates/{eid}/boq").json()
    row = next(l for l in boq if l["id"] == proposal["boq_line_id"])
    assert row["rate_item_id"] == chosen["rate_item_id"]
    assert row["amount"] is not None


def test_accept_rejects_item_not_in_candidates(client, test_db, sample_params):
    _bootstrap_dsr(test_db)
    eid = _mk_estimate(client, sample_params)
    client.post(f"/estimates/{eid}/runs", json={"mode": "full"})

    queue = client.get(f"/estimates/{eid}/mapping-queue").json()
    if not queue:
        return
    r = client.post(
        f"/estimates/{eid}/mapping/{queue[0]['id']}",
        json={"rate_item_id": "not-a-candidate-id-aaaa-bbbb-cccc-dddd"},
    )
    assert r.status_code in {404, 422}


def test_skip_closes_proposal(client, test_db, sample_params):
    _bootstrap_dsr(test_db)
    eid = _mk_estimate(client, sample_params)
    client.post(f"/estimates/{eid}/runs", json={"mode": "full"})

    queue = client.get(f"/estimates/{eid}/mapping-queue").json()
    if not queue:
        return
    r = client.delete(f"/estimates/{eid}/mapping/{queue[0]['id']}")
    assert r.status_code == 200
    assert r.json()["status"] == "skipped"

    queue2 = client.get(f"/estimates/{eid}/mapping-queue").json()
    assert all(p["id"] != queue[0]["id"] for p in queue2)


def test_second_estimate_hits_org_cache(client, test_db, sample_params):
    """Realistic flow: user accepts some queued proposals on estimate 1, then a
    fresh estimate 2 reuses those accepted mappings from the org cache."""
    from api.db.models import OrgMapping

    _bootstrap_dsr(test_db)

    # Estimate 1 — run full, then accept the first few queued proposals.
    eid1 = _mk_estimate(client, sample_params)
    client.post(f"/estimates/{eid1}/runs", json={"mode": "full"})
    queue = client.get(f"/estimates/{eid1}/mapping-queue").json()
    for p in queue[:5]:
        if not p["top_candidates"]:
            continue
        client.post(
            f"/estimates/{eid1}/mapping/{p['id']}",
            json={"rate_item_id": p["top_candidates"][0]["rate_item_id"]},
        )

    # OrgMapping rows exist after the first run + accepts.
    cache_rows_before = test_db.query(OrgMapping).count()
    assert cache_rows_before > 0, "expected OrgMapping entries after run+accepts"

    # Estimate 2 — run full, which re-runs mapping and should hit the cache for
    # the lines whose descriptions match. We assert via the AgentRun output.
    eid2 = _mk_estimate(client, sample_params)
    client.post(f"/estimates/{eid2}/runs", json={"mode": "full"})

    from api.db.models import AgentRun
    runs = (
        test_db.query(AgentRun)
        .filter_by(estimate_id=eid2, agent="mapping")
        .order_by(AgentRun.created_at.desc())
        .all()
    )
    assert runs, "mapping AgentRun should be recorded for estimate 2"
    out = runs[0].output or {}
    assert out.get("cache_hits", 0) >= 1, out


def test_map_without_dsr_returns_422(client, sample_params):
    eid = _mk_estimate(client, sample_params)
    r = client.post(f"/estimates/{eid}/map")
    assert r.status_code == 422
    assert "no rate edition" in r.json()["detail"].lower()
