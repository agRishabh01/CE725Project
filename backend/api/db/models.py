"""SQLAlchemy models for the 12 PDR entities.

Column shapes match PDR §Data model. Tenancy (org_id) is present from day 1
but single-org in Phase 1-2; RLS is wired in Phase 4 (W20).

Portability note: JSON column uses SQLAlchemy's generic JSON type so Alembic
can map it to SQLite TEXT (dev) and Postgres JSONB (Phase 4).
Embeddings are stored as LargeBinary in Phase 1-2 and migrated to pgvector
in W17.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from api.db.types import EmbeddingVector


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


# ------------------------------------------------------------------- Organization
class Organization(Base):
    __tablename__ = "organization"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default="free")
    default_rate_edition_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("rate_edition.id", use_alter=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    users: Mapped[list[User]] = relationship(back_populates="organization")
    projects: Mapped[list[Project]] = relationship(back_populates="organization")


# ------------------------------------------------------------------- User
class User(Base):
    __tablename__ = "user"
    __table_args__ = (
        CheckConstraint(
            "role in ('admin','estimator','reviewer','viewer')", name="ck_user_role"
        ),
        UniqueConstraint("org_id", "email", name="uq_user_org_email"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organization.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="estimator")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    organization: Mapped[Organization] = relationship(back_populates="users")


# ------------------------------------------------------------------- Project
class Project(Base):
    __tablename__ = "project"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organization.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str | None] = mapped_column(String(200))
    use_type: Mapped[str | None] = mapped_column(String(50))
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    organization: Mapped[Organization] = relationship(back_populates="projects")
    estimates: Mapped[list[Estimate]] = relationship(back_populates="project")


# ------------------------------------------------------------------- Estimate
class Estimate(Base):
    __tablename__ = "estimate"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("project.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    rule_set_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("rule_set.id"))
    rate_edition_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("rate_edition.id"))
    cost_index: Mapped[float] = mapped_column(Float, default=1.0)
    contingency_pct: Mapped[float] = mapped_column(Float, default=3.0)
    prelims_pct: Mapped[float] = mapped_column(Float, default=2.0)
    total_cost: Mapped[float | None] = mapped_column(Float)
    totals_by_element: Mapped[dict | None] = mapped_column(JSON)
    scenario_label: Mapped[str | None] = mapped_column(String(100))
    base_estimate_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("estimate.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    project: Mapped[Project] = relationship(back_populates="estimates")
    boq_lines: Mapped[list[BOQLine]] = relationship(
        back_populates="estimate", cascade="all, delete-orphan"
    )
    building_params: Mapped[BuildingParams | None] = relationship(
        back_populates="estimate", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "status in ('draft','in_review','approved')", name="ck_estimate_status"
        ),
    )


# ------------------------------------------------------------------- BuildingParams
class BuildingParams(Base):
    __tablename__ = "building_params"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    estimate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("estimate.id"), unique=True, nullable=False
    )
    inputs: Mapped[dict] = mapped_column(JSON, nullable=False)
    confidence: Mapped[dict | None] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(20), default="form")

    estimate: Mapped[Estimate] = relationship(back_populates="building_params")

    __table_args__ = (
        CheckConstraint("source in ('form','text','plan')", name="ck_params_source"),
    )


# ------------------------------------------------------------------- BOQLine
class BOQLine(Base):
    __tablename__ = "boq_line"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    estimate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("estimate.id"), nullable=False
    )
    element: Mapped[str] = mapped_column(String(50), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    rate: Mapped[float | None] = mapped_column(Float)
    amount: Mapped[float | None] = mapped_column(Float)
    rate_item_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("rate_item.id"))
    formula_trace: Mapped[dict | None] = mapped_column(JSON)
    override_reason: Mapped[str | None] = mapped_column(Text)
    is_overridden: Mapped[bool] = mapped_column(default=False)

    estimate: Mapped[Estimate] = relationship(back_populates="boq_lines")

    __table_args__ = (Index("ix_boqline_estimate_element", "estimate_id", "element"),)


# ------------------------------------------------------------------- RateEdition
class RateEdition(Base):
    __tablename__ = "rate_edition"
    __table_args__ = (
        UniqueConstraint("source", "region", "year", name="uq_edition"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "CPWD DSR"
    region: Mapped[str | None] = mapped_column(String(50))
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_date: Mapped[datetime | None] = mapped_column(Date)
    file_hash: Mapped[str | None] = mapped_column(String(64))
    scope: Mapped[str] = mapped_column(String(10), default="global")  # 'global' | 'org'
    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organization.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    items: Mapped[list[RateItem]] = relationship(
        back_populates="edition", cascade="all, delete-orphan"
    )


# ------------------------------------------------------------------- RateItem
class RateItem(Base):
    __tablename__ = "rate_item"
    __table_args__ = (
        UniqueConstraint("edition_id", "item_no", name="uq_item_per_edition"),
        Index("ix_rateitem_chapter_unit", "chapter", "unit"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    edition_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rate_edition.id"), nullable=False
    )
    item_no: Mapped[str] = mapped_column(String(50), nullable=False)
    chapter: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    rate: Mapped[float] = mapped_column(Float, nullable=False)
    # Postgres: native vector(1024) with cosine indexing. SQLite tests fall back
    # to a packed-bytes BLOB. See api/db/types.EmbeddingVector.
    embedding = mapped_column(EmbeddingVector, nullable=True)

    edition: Mapped[RateEdition] = relationship(back_populates="items")


# ------------------------------------------------------------------- CostIndex
class CostIndex(Base):
    __tablename__ = "cost_index"
    __table_args__ = (
        UniqueConstraint("region", "base_edition_id", "effective_date", name="uq_costindex"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    base_edition_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rate_edition.id"), nullable=False
    )
    index_pct: Mapped[float] = mapped_column(Float, nullable=False)  # e.g. 1.15 for +15%
    effective_date: Mapped[datetime] = mapped_column(Date, nullable=False)


# ------------------------------------------------------------------- RuleSet
class RuleSet(Base):
    __tablename__ = "rule_set"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organization.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    rules: Mapped[dict] = mapped_column(JSON, nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("rule_set.id"))
    label: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ------------------------------------------------------------------- ValidationCase
class ValidationCase(Base):
    __tablename__ = "validation_case"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    estimate_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("estimate.id"))
    reference_source: Mapped[str] = mapped_column(String(200), nullable=False)
    element_totals: Mapped[dict] = mapped_column(JSON, nullable=False)
    item_quantities: Mapped[dict | None] = mapped_column(JSON)
    split: Mapped[str] = mapped_column(String(20), default="calibration")  # 'calibration'|'held_out'
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    __table_args__ = (
        CheckConstraint("split in ('calibration','held_out')", name="ck_case_split"),
    )


# ------------------------------------------------------------------- AgentRun
class AgentRun(Base):
    __tablename__ = "agent_run"
    __table_args__ = (Index("ix_agentrun_estimate", "estimate_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    estimate_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("estimate.id"))
    agent: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100))
    input: Mapped[dict | None] = mapped_column(JSON)
    output: Mapped[dict | None] = mapped_column(JSON)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_inr: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="running")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ------------------------------------------------------------------ MappingProposal
class MappingProposal(Base):
    """Low-confidence rate-mapping proposals awaiting human review.

    One row per BOQ line that the mapping agent could not confidently resolve.
    Top candidates are stored as JSON so the review UI needs no join explosion.
    """

    __tablename__ = "mapping_proposal"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending','accepted','skipped')", name="ck_proposal_status"
        ),
        Index("ix_proposal_estimate_status", "estimate_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    estimate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("estimate.id"), nullable=False
    )
    boq_line_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("boq_line.id"), nullable=False
    )
    # list of {rate_item_id, item_no, chapter, description, unit, rate, score}
    top_candidates: Mapped[list] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    strategy: Mapped[str] = mapped_column(String(20), default="deterministic")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    accepted_rate_item_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("rate_item.id")
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ------------------------------------------------------------------ OrgMapping
class OrgMapping(Base):
    """Accepted-match cache per organization.

    When a user accepts a candidate for a given description, we remember it so
    subsequent estimates of the same shape skip the LLM entirely (PDR §Rate mapping).
    Keyed on a normalised SHA-256 hash of the description + unit + edition.
    """

    __tablename__ = "org_mapping"
    __table_args__ = (
        UniqueConstraint(
            "org_id", "description_hash", "edition_id",
            name="uq_org_mapping",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organization.id"), nullable=False)
    edition_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rate_edition.id"), nullable=False
    )
    description_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    rate_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rate_item.id"), nullable=False
    )
    accepted_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"))
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
