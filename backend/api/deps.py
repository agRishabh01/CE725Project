"""Shared FastAPI dependencies: DB session, default org, default user."""
from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

from api.db.models import Organization, User
from api.db.session import SessionLocal

DEFAULT_ORG_NAME = "Default Org"
DEFAULT_USER_EMAIL = "dev@localhost"


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_default_tenant(db: Session) -> tuple[Organization, User]:
    """Create a single-user default org + user on first use.

    In Phase 4 this disappears — orgs/users come from OIDC claims and the
    tenancy layer. For Phases 1-3 it's the implicit tenant for every request.
    """
    org = db.query(Organization).filter_by(name=DEFAULT_ORG_NAME).one_or_none()
    if org is None:
        org = Organization(name=DEFAULT_ORG_NAME, plan="free")
        db.add(org)
        db.flush()
    user = db.query(User).filter_by(org_id=org.id, email=DEFAULT_USER_EMAIL).one_or_none()
    if user is None:
        user = User(org_id=org.id, email=DEFAULT_USER_EMAIL, role="admin")
        db.add(user)
        db.flush()
    db.commit()
    return org, user


def current_tenant(db: Session = Depends(get_db)) -> tuple[Organization, User]:
    return ensure_default_tenant(db)
