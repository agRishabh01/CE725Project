"""Rate-item search endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth import ApiKeyDep
from api.db.models import RateEdition
from api.deps import get_db
from api.services.rate_search import SearchHit, ensure_fts_index, search_rates

router = APIRouter(tags=["rates"], dependencies=[ApiKeyDep])


class RateEditionOut(BaseModel):
    id: str
    source: str
    region: str | None
    year: int
    scope: str


class SearchHitOut(BaseModel):
    item_id: str
    item_no: str
    chapter: str
    description: str
    unit: str
    rate: float
    bm25_score: float
    cosine_score: float
    combined_score: float

    @classmethod
    def from_hit(cls, h: SearchHit) -> "SearchHitOut":
        return cls(
            item_id=h.item_id, item_no=h.item_no, chapter=h.chapter,
            description=h.description, unit=h.unit, rate=h.rate,
            bm25_score=h.bm25_score, cosine_score=h.cosine_score,
            combined_score=h.combined_score,
        )


@router.get("/rate-editions", response_model=list[RateEditionOut])
def list_rate_editions(db: Session = Depends(get_db)) -> list[RateEditionOut]:
    rows = db.query(RateEdition).order_by(RateEdition.year.desc()).all()
    return [
        RateEditionOut(
            id=r.id, source=r.source, region=r.region, year=r.year, scope=r.scope,
        )
        for r in rows
    ]


@router.get("/rate-items/search", response_model=list[SearchHitOut])
def search_rate_items(
    q: str = Query(..., min_length=1),
    edition: str = Query(..., alias="edition"),
    unit: str | None = None,
    chapter: str | None = None,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> list[SearchHitOut]:
    exists = db.query(RateEdition).filter_by(id=edition).one_or_none()
    if exists is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "edition not found")
    ensure_fts_index(db)
    hits = search_rates(
        db, query=q, edition_id=edition, unit=unit, chapter=chapter, limit=limit,
    )
    return [SearchHitOut.from_hit(h) for h in hits]
