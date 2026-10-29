"""Compute embeddings for rate-item descriptions via OpenRouter.

Two modes selected by env:
  - OPENROUTER_API_KEY set  → `openai` SDK pointed at OpenRouter, using
                               OPENROUTER_EMBED_MODEL (default
                               `openai/text-embedding-3-small`) truncated to
                               OPENROUTER_EMBED_DIM dims (default 1024).
  - Not set                 → a deterministic hash-based pseudo-embedding.
                               Useful for CI and offline dev; not meaningful
                               for real semantic search.

Vectors are L2-normalised float32 numpy arrays of length `EMBED_DIM`. The
`EmbeddingVector` TypeDecorator (api/db/types.py) handles dialect packing.
"""
from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Iterable, Iterator

import numpy as np

from api.db.types import EMBED_DIM

_WORD_RE = re.compile(r"[a-z]+", re.IGNORECASE)


def _pseudo_embed_one(text: str) -> np.ndarray:
    """Deterministic hash-based pseudo embedding — only useful for dev/tests."""
    v = np.zeros(EMBED_DIM, dtype=np.float32)
    for word in _WORD_RE.findall(text.lower()):
        if len(word) < 3:
            continue
        h = hashlib.blake2b(word.encode("utf-8"), digest_size=4).digest()
        idx = int.from_bytes(h, "big") % EMBED_DIM
        v[idx] += 1.0
    norm = float(np.linalg.norm(v))
    if norm > 0:
        v /= norm
    return v


def _openrouter_embed_batch(texts: list[str], api_key: str) -> list[np.ndarray]:
    from openai import OpenAI

    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    model = os.getenv("OPENROUTER_EMBED_MODEL", "openai/text-embedding-3-small")
    dim = int(os.getenv("OPENROUTER_EMBED_DIM", str(EMBED_DIM)))

    default_headers: dict[str, str] = {}
    referer = os.getenv("OPENROUTER_HTTP_REFERER")
    title = os.getenv("OPENROUTER_APP_TITLE")
    if referer:
        default_headers["HTTP-Referer"] = referer
    if title:
        default_headers["X-Title"] = title

    client = OpenAI(
        api_key=api_key, base_url=base_url,
        default_headers=default_headers or None,
    )
    kwargs: dict = {"model": model, "input": texts}
    # text-embedding-3-* supports the `dimensions` argument; other models ignore it.
    if "text-embedding-3" in model:
        kwargs["dimensions"] = dim

    resp = client.embeddings.create(**kwargs)
    out: list[np.ndarray] = []
    for item in resp.data:
        arr = np.array(item.embedding, dtype=np.float32)
        if arr.shape[0] != EMBED_DIM:
            # If the provider returned a different dim (ignored `dimensions`),
            # pad or truncate so pgvector(1024) accepts it.
            fixed = np.zeros(EMBED_DIM, dtype=np.float32)
            fixed[: min(arr.shape[0], EMBED_DIM)] = arr[: min(arr.shape[0], EMBED_DIM)]
            arr = fixed
        n = float(np.linalg.norm(arr))
        if n > 0:
            arr = arr / n
        out.append(arr)
    return out


def embed_texts(texts: Iterable[str]) -> Iterator[np.ndarray]:
    """Stream L2-normalised float32 arrays of shape (EMBED_DIM,) for each text."""
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    batch: list[str] = list(texts)
    if not batch:
        return
    # A placeholder key counts as "unset" so tests + offline dev stay deterministic.
    if api_key and not api_key.startswith("sk-or-replace"):
        for i in range(0, len(batch), 32):
            yield from _openrouter_embed_batch(batch[i : i + 32], api_key)
    else:
        for t in batch:
            yield _pseudo_embed_one(t)


def to_blob(vec: np.ndarray) -> bytes:
    return vec.astype(np.float32).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine on already-L2-normalised vectors reduces to a dot product."""
    if a.shape != b.shape:
        return 0.0
    return float(np.dot(a, b))
