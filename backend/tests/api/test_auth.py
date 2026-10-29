"""API-key auth modes: dev-no-auth, enabled-and-valid, enabled-and-missing."""
from __future__ import annotations


def test_health_is_public(client):
    r = client.get("/health")
    assert r.status_code == 200


def test_projects_open_when_no_api_key_set(client):
    r = client.get("/projects")
    assert r.status_code == 200
    assert r.json() == []


def test_projects_require_key_when_env_set(client, monkeypatch):
    monkeypatch.setenv("API_KEY", "s3cret")
    r = client.get("/projects")
    assert r.status_code == 401

    r2 = client.get("/projects", headers={"X-API-Key": "wrong"})
    assert r2.status_code == 401

    r3 = client.get("/projects", headers={"X-API-Key": "s3cret"})
    assert r3.status_code == 200
