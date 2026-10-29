"""Rate-item search endpoint + xlsx export."""
from __future__ import annotations

from pathlib import Path

from api.services.rate_import import import_from_yaml

SAMPLE_DSR = (
    Path(__file__).resolve().parents[2] / "data" / "cpwd_dsr_2023" / "sample.yaml"
)


def _preload_dsr(client, test_db) -> str:
    edition = import_from_yaml(test_db, SAMPLE_DSR)
    return edition.id


def test_rate_search_endpoint(client, test_db):
    eid = _preload_dsr(client, test_db)
    r = client.get("/rate-items/search", params={"q": "RCC M25 columns", "edition": eid, "unit": "m3", "limit": 5})
    assert r.status_code == 200, r.text
    hits = r.json()
    assert hits
    assert any(h["item_no"] == "2.2.2" for h in hits[:3])


def test_rate_search_unknown_edition_404(client):
    r = client.get("/rate-items/search", params={"q": "anything", "edition": "no-such-edition"})
    assert r.status_code == 404


def test_list_rate_editions(client, test_db):
    _preload_dsr(client, test_db)
    r = client.get("/rate-editions")
    assert r.status_code == 200
    rows = r.json()
    assert any(e["source"] == "CPWD DSR" for e in rows)


def test_export_xlsx_after_run(client, sample_params):
    pid = client.post("/projects", json={"name": "ExportTest"}).json()["id"]
    eid = client.post(
        f"/projects/{pid}/estimates", json={"params": sample_params, "cost_index": 1.0}
    ).json()["id"]
    client.post(f"/estimates/{eid}/runs", json={"mode": "full"})

    r = client.get(f"/estimates/{eid}/export", params={"format": "xlsx"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert r.headers.get("content-disposition", "").startswith("attachment")
    # xlsx is a zip; first bytes must be PK\x03\x04.
    assert r.content[:4] == b"PK\x03\x04"


def test_export_without_run_422(client, sample_params):
    pid = client.post("/projects", json={"name": "EmptyExport"}).json()["id"]
    eid = client.post(
        f"/projects/{pid}/estimates", json={"params": sample_params}
    ).json()["id"]
    r = client.get(f"/estimates/{eid}/export", params={"format": "xlsx"})
    assert r.status_code == 422
