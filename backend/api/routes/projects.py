"""Projects CRUD + dashboard summary."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth import ApiKeyDep
from api.db.models import BuildingParams, Estimate, Organization, Project, User
from api.deps import current_tenant, get_db
from api.schemas.project import ProjectCreate, ProjectOut

router = APIRouter(prefix="/projects", tags=["projects"], dependencies=[ApiKeyDep])


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    tenant: tuple[Organization, User] = Depends(current_tenant),
) -> ProjectOut:
    org, user = tenant
    p = Project(
        org_id=org.id,
        name=payload.name,
        location=payload.location,
        use_type=payload.use_type,
        created_by=user.id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return ProjectOut.model_validate(p, from_attributes=True)


@router.get("", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    tenant: tuple[Organization, User] = Depends(current_tenant),
) -> list[ProjectOut]:
    org, _ = tenant
    rows = (
        db.query(Project)
        .filter(Project.org_id == org.id)
        .order_by(Project.created_at.desc())
        .all()
    )
    return [ProjectOut.model_validate(r, from_attributes=True) for r in rows]


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    tenant: tuple[Organization, User] = Depends(current_tenant),
) -> ProjectOut:
    org, _ = tenant
    p = db.query(Project).filter(Project.id == project_id, Project.org_id == org.id).one_or_none()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return ProjectOut.model_validate(p, from_attributes=True)


# ------------------------------------------------------- dashboard summary
class ProjectEstimatePoint(BaseModel):
    estimate_id: str
    created_at: datetime
    total_inr: float | None
    cost_per_m2: float | None


class ProjectSummary(BaseModel):
    id: str
    name: str
    location: str | None
    use_type: str | None
    created_at: datetime
    estimate_count: int
    latest_total_inr: float | None
    latest_cost_per_m2: float | None
    series: list[ProjectEstimatePoint]


@router.get("/-/summary", response_model=list[ProjectSummary])
def list_project_summaries(
    db: Session = Depends(get_db),
    tenant: tuple[Organization, User] = Depends(current_tenant),
) -> list[ProjectSummary]:
    """Dashboard payload — one row per project with its estimate time-series.

    `-/summary` doesn't collide with any project id. Each series is in
    chronological order so the sparkline renders left-to-right.
    """
    org, _ = tenant
    projects = (
        db.query(Project)
        .filter(Project.org_id == org.id)
        .order_by(Project.created_at.desc())
        .all()
    )
    out: list[ProjectSummary] = []
    for p in projects:
        estimates = (
            db.query(Estimate)
            .filter(Estimate.project_id == p.id)
            .order_by(Estimate.created_at.asc())
            .all()
        )
        series: list[ProjectEstimatePoint] = []
        for e in estimates:
            bp = db.query(BuildingParams).filter_by(estimate_id=e.id).one_or_none()
            builtup = None
            if bp and isinstance(bp.inputs, dict):
                try:
                    builtup = float(bp.inputs.get("builtup_area_m2") or 0.0)
                except (TypeError, ValueError):
                    builtup = None
            cost_per_m2 = (
                round((e.total_cost or 0.0) / builtup, 2)
                if builtup and builtup > 0 and e.total_cost
                else None
            )
            series.append(ProjectEstimatePoint(
                estimate_id=e.id, created_at=e.created_at,
                total_inr=e.total_cost, cost_per_m2=cost_per_m2,
            ))
        out.append(ProjectSummary(
            id=p.id, name=p.name, location=p.location, use_type=p.use_type,
            created_at=p.created_at,
            estimate_count=len(series),
            latest_total_inr=series[-1].total_inr if series else None,
            latest_cost_per_m2=series[-1].cost_per_m2 if series else None,
            series=series,
        ))
    return out
