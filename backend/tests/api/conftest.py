"""API tests use a fresh in-memory SQLite per test, injected via dependency_overrides."""
from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from api.db.models import Base
from api.deps import get_db
from api.main import app


@pytest.fixture
def api_env(monkeypatch):
    """Isolate tests from the dev .env.

    - API_KEY unset: dev-no-auth routes.
    - OPENROUTER_API_KEY unset: forces the deterministic mapping path so
      tests don't try to hit the live OpenRouter API.
    """
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    yield


@pytest.fixture
def test_db() -> Iterator[Session]:
    """A single in-memory SQLite shared across the test's requests via one connection."""
    # StaticPool keeps the one connection alive so :memory: survives between requests.
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db = Session_()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture
def client(test_db: Session, api_env) -> Iterator[TestClient]:
    def _override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def sample_params() -> dict:
    return {
        "use_type": "hostel",
        "plot_area_m2": 1800.0,
        "builtup_area_m2": 3000.0,
        "floors": 5,
        "floor_height_m": 3.0,
        "aspect_ratio": 1.5,
        "structural_system": "rcc_framed",
        "spec_level": "standard",
        "sbc_kpa": 150.0,
        "plan_shape": "rectangular",
        "location": "Mumbai",
        "source": "form",
    }
