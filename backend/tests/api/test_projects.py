"""Projects CRUD and tenancy."""
from __future__ import annotations


def test_create_and_list_project(client):
    r = client.post(
        "/projects",
        json={"name": "Pilot building", "location": "Delhi", "use_type": "residential"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Pilot building"
    assert body["id"]

    r2 = client.get("/projects")
    assert r2.status_code == 200
    assert len(r2.json()) == 1
    assert r2.json()[0]["id"] == body["id"]


def test_get_project_404_on_bogus_id(client):
    r = client.get("/projects/no-such-id")
    assert r.status_code == 404


def test_project_name_required(client):
    r = client.post("/projects", json={"location": "Delhi"})
    assert r.status_code == 422
    body = r.json()
    assert "errors" in body
    assert any("name" in e["loc"] for e in body["errors"])
