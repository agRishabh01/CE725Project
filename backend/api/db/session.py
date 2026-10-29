"""SQLAlchemy engine + session factory.

Default: Postgres via `postgresql+psycopg://`. Tests use in-memory SQLite via
their own fixture; dialect-specific code (FTS5, pgvector) branches on
`engine.dialect.name`.
"""
from __future__ import annotations

import os
from collections.abc import Iterator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://ce725:ce725@localhost:5432/ce725",
)

# Default `postgresql://` resolves to psycopg2; this project installs
# psycopg (v3). Rewrite so a plain `postgresql://` URL still works.
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://"):]

_connect_args: dict = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False

engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
