"""Export endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from api.auth import ApiKeyDep
from api.db.models import Organization, User
from api.deps import current_tenant, get_db
from api.routes.estimates import _get_estimate
from api.services.export_xlsx import estimate_to_xlsx

router = APIRouter(tags=["exports"], dependencies=[ApiKeyDep])


@router.get("/estimates/{estimate_id}/export")
def export_estimate(
    estimate_id: str,
    format: str = Query("xlsx", pattern="^(xlsx)$"),
    db: Session = Depends(get_db),
    tenant: tuple[Organization, User] = Depends(current_tenant),
) -> Response:
    org, _ = tenant
    est = _get_estimate(db, estimate_id, org.id)
    if not est.boq_lines:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "estimate has no BOQ lines yet — start a run first",
        )
    content = estimate_to_xlsx(est, db)
    filename = f"estimate-{est.id[:8]}.xlsx"
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
