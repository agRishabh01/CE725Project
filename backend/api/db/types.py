"""Dialect-aware column types.

`EmbeddingVector` lets the same ORM model work on:
  - Postgres  → `vector(dim)` native type from pgvector; proper <=> indexing.
  - SQLite    → `BLOB` holding packed float32 bytes; used only by in-memory
                test DBs, which do cosine in Python.

Call sites always receive/pass a numpy `float32` 1-D array; the type decorator
handles packing on the way to the dialect.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from sqlalchemy import LargeBinary
from sqlalchemy.types import TypeDecorator


EMBED_DIM = 1024


class EmbeddingVector(TypeDecorator):
    """Store a 1024-float embedding as `vector(1024)` on Postgres, BLOB on SQLite.

    We accept either `np.ndarray[float32]`, `list[float]`, or raw `bytes`
    (legacy LargeBinary rows from pre-Postgres migrations). We return
    `np.ndarray[float32]` on both dialects for symmetric consumer code.
    """

    impl = LargeBinary
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(EMBED_DIM))
        return dialect.type_descriptor(LargeBinary())

    # ------------------------------------------------------------- bind
    def process_bind_param(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        if dialect.name == "postgresql":
            # pgvector.sqlalchemy.Vector accepts list[float] or np.ndarray.
            if isinstance(value, bytes):
                return np.frombuffer(value, dtype=np.float32).tolist()
            if hasattr(value, "tolist"):
                return value.astype(np.float32).tolist()
            return list(value)
        # SQLite path — pack to bytes.
        if isinstance(value, bytes):
            return value
        if hasattr(value, "astype"):
            return value.astype(np.float32).tobytes()
        return np.array(value, dtype=np.float32).tobytes()

    # ----------------------------------------------------------- result
    def process_result_value(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        if dialect.name == "postgresql":
            # pgvector returns a list of floats.
            return np.asarray(value, dtype=np.float32)
        # SQLite BLOB → bytes → np.ndarray.
        return np.frombuffer(value, dtype=np.float32)
