"""Tools the mapping agent can call.

Each tool pairs an OpenAI function-calling schema with a Python implementation
that runs against the SQLAlchemy session. The deterministic agent calls the
Python side directly; the LLM agent (OpenRouter + any OpenAI-compatible model)
exposes the schemas to the model and dispatches `tool_calls` back here.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from sqlalchemy.orm import Session

from api.db.models import CostIndex, RateItem
from api.services.rate_search import SearchHit, search_rates


# OpenAI function-calling format: list of {type: "function", function: {...}}.
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_rates",
            "description": (
                "Hybrid keyword + semantic search for schedule-of-rates items. "
                "Use the BOQ line description as the query. Filter by `unit` to "
                "improve precision. Returns up to `limit` candidates with "
                "item_no, chapter, description, unit, rate and a combined score."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The BOQ line description to match.",
                    },
                    "edition_id": {"type": "string"},
                    "unit": {
                        "type": "string",
                        "description": "Required engine unit filter: m, m2, m3, kg, nos.",
                    },
                    "chapter": {"type": "string"},
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 25,
                    },
                },
                "required": ["query", "edition_id", "unit"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_rate_item",
            "description": "Fetch one rate item by ID. Use when the full description is needed.",
            "parameters": {
                "type": "object",
                "properties": {"item_id": {"type": "string"}},
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cost_index",
            "description": "Look up the location + date cost-index multiplier for a region.",
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {"type": "string"},
                    "edition_id": {"type": "string"},
                },
                "required": ["region", "edition_id"],
            },
        },
    },
]


# ------------------------------------------------------------- implementations
def tool_search_rates(db: Session, **kwargs: Any) -> dict:
    query = kwargs["query"]
    edition_id = kwargs["edition_id"]
    unit = kwargs.get("unit")
    chapter = kwargs.get("chapter")
    limit = int(kwargs.get("limit", 10))
    hits: list[SearchHit] = search_rates(
        db,
        query=query,
        edition_id=edition_id,
        unit=unit,
        chapter=chapter,
        limit=limit,
    )
    return {"results": [_hit_to_dict(h) for h in hits]}


def tool_get_rate_item(db: Session, **kwargs: Any) -> dict:
    item_id = kwargs["item_id"]
    item = db.query(RateItem).filter(RateItem.id == item_id).one_or_none()
    if item is None:
        return {"error": f"rate item {item_id!r} not found"}
    return {
        "id": item.id,
        "item_no": item.item_no,
        "chapter": item.chapter,
        "description": item.description,
        "unit": item.unit,
        "rate": item.rate,
    }


def tool_get_cost_index(db: Session, **kwargs: Any) -> dict:
    region = kwargs["region"]
    edition_id = kwargs["edition_id"]
    row = (
        db.query(CostIndex)
        .filter(CostIndex.region == region, CostIndex.base_edition_id == edition_id)
        .order_by(CostIndex.effective_date.desc())
        .first()
    )
    if row is None:
        return {"region": region, "index_pct": 1.0, "fallback": True}
    return {
        "region": row.region,
        "index_pct": row.index_pct,
        "effective_date": row.effective_date.isoformat(),
    }


def dispatch(db: Session, tool_name: str, tool_input: dict) -> dict:
    """Route an OpenAI tool_call payload to the right implementation."""
    if tool_name == "search_rates":
        return tool_search_rates(db, **tool_input)
    if tool_name == "get_rate_item":
        return tool_get_rate_item(db, **tool_input)
    if tool_name == "get_cost_index":
        return tool_get_cost_index(db, **tool_input)
    return {"error": f"unknown tool: {tool_name}"}


def _hit_to_dict(h: SearchHit) -> dict:
    d = asdict(h)
    d.pop("bm25_score", None)
    d.pop("cosine_score", None)
    return d
