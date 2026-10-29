"""Minimal single-user API-key auth for Weeks 5-16.

Semantics:
  - If API_KEY env var is set, requests must send `X-API-Key: <key>`; mismatch → 401.
  - If API_KEY is unset or empty, auth is bypassed (dev convenience).

Replaced in W18 by Auth.js + OIDC + per-user JWT. Replaced in W20 by role-gated
org tenancy. This file intentionally stays simple so the swap is one import away.
"""
from __future__ import annotations

import os

from fastapi import Depends, Header, HTTPException, status


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("API_KEY", "").strip()
    if not expected:
        return  # dev mode — no auth
    if not x_api_key or x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-API-Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )


ApiKeyDep = Depends(require_api_key)
