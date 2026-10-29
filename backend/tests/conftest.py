"""Shared pytest fixtures. In-memory SQLite + fresh schema per test session."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.db.models import Base


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Keep dev `.env` values from leaking into tests.

    - API_KEY unset → routes run in dev-no-auth mode.
    - OPENROUTER_API_KEY unset → mapping agent + embeddings stay deterministic.
    """
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture
def db_session():
    """Fresh SQLite in-memory DB per test with the full schema baked in."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
