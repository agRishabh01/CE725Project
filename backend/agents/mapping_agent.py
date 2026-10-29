"""Rate-mapping agent.

Two execution modes selected automatically:
  - **LLM mode** when `OPENROUTER_API_KEY` is set: `openai` SDK pointed at
    OpenRouter, calling `OPENROUTER_MODEL` (default `google/gemini-2.0-flash-001`).
    Driven through a tool-use loop with the schemas in `agents/tools.py`. The
    agent must ground its picks to IDs returned by `search_rates` (hard rule
    in the system prompt).
  - **Deterministic mode** otherwise: no network. Uses hybrid search's
    `combined_score` directly, with per-chapter heuristics for tie-breaking.

Both paths share the same per-line proposal shape, so the review UI doesn't
care which produced it.

High-confidence matches (confidence ≥ 0.75) auto-apply:
  - BOQ line's `rate_item_id`, `rate`, and `amount` are updated.
  - An `OrgMapping` row is written so the same description short-circuits the
    LLM next time (PDR §Rate mapping cache).

Low-confidence matches land as `MappingProposal` rows for human review.
"""
from __future__ import annotations

import hashlib
import json as _json
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

import numpy as np

from agents import tools
from api.db.models import (
    AgentRun,
    BOQLine,
    Estimate,
    MappingProposal,
    OrgMapping,
    RateEdition,
    RateItem,
)
from api.services.embeddings import embed_texts
from api.services.rate_search import search_rates

AUTO_APPLY_THRESHOLD = 0.75
BATCH_SIZE = 20


# ---------------------------------------------------------------- proposal shape
@dataclass(frozen=True, slots=True)
class Candidate:
    rate_item_id: str
    item_no: str
    chapter: str
    description: str
    unit: str
    rate: float
    score: float

    def to_dict(self) -> dict:
        return {
            "rate_item_id": self.rate_item_id,
            "item_no": self.item_no,
            "chapter": self.chapter,
            "description": self.description,
            "unit": self.unit,
            "rate": self.rate,
            "score": self.score,
        }


@dataclass(frozen=True, slots=True)
class LineProposal:
    boq_line_id: str
    candidates: list[Candidate]
    confidence: float
    reason: str
    strategy: str


@dataclass(frozen=True, slots=True)
class MappingResult:
    estimate_id: str
    edition_id: str
    strategy: str
    processed: int
    auto_applied: int
    queued: int
    cache_hits: int
    duration_s: float


# ---------------------------------------------------------------- normalisation
def normalise_description(desc: str, unit: str) -> str:
    """Lower, collapse whitespace, strip punctuation — stable org-cache key."""
    s = re.sub(r"[^a-z0-9 ]+", " ", desc.lower())
    s = re.sub(r"\s+", " ", s).strip()
    return f"{s}|{unit.lower()}"


def description_hash(desc: str, unit: str) -> str:
    return hashlib.sha256(normalise_description(desc, unit).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- deterministic
def _deterministic_proposal(
    db: Session,
    line: BOQLine,
    edition_id: str,
    query_vector: np.ndarray | None = None,
) -> LineProposal:
    """Rank by hybrid search's combined_score with simple heuristics.

    `query_vector` lets map_estimate pre-batch all BOQ-line query embeddings
    into a single OpenRouter call rather than one per line.
    """
    hits_raw = search_rates(
        db,
        query=line.description,
        edition_id=edition_id,
        unit=line.unit,
        limit=10,
        query_vector=query_vector,
    )
    hits = [
        {
            "item_id": h.item_id, "item_no": h.item_no, "chapter": h.chapter,
            "description": h.description, "unit": h.unit, "rate": h.rate,
            "combined_score": h.combined_score,
        }
        for h in hits_raw
    ]
    top = hits[:3]
    candidates = [
        Candidate(
            rate_item_id=h["item_id"],
            item_no=h["item_no"],
            chapter=h["chapter"],
            description=h["description"],
            unit=h["unit"],
            rate=h["rate"],
            score=h["combined_score"],
        )
        for h in top
    ]
    if not candidates:
        return LineProposal(
            boq_line_id=line.id, candidates=[], confidence=0.0,
            reason="no candidates with matching unit",
            strategy="deterministic",
        )
    best = candidates[0]
    # Boost score when the second candidate is clearly worse — exclusivity signal.
    exclusivity = 0.0
    if len(candidates) > 1:
        exclusivity = max(0.0, best.score - candidates[1].score) * 0.5
    confidence = min(1.0, best.score + exclusivity)
    reason = (
        f"hybrid search ranked {best.item_no} top with score {best.score:.2f}"
        + (f"; next best {candidates[1].score:.2f} ({candidates[1].item_no})" if len(candidates) > 1 else "")
    )
    return LineProposal(
        boq_line_id=line.id, candidates=candidates, confidence=confidence,
        reason=reason, strategy="deterministic",
    )


# ---------------------------------------------------------------- LLM (OpenRouter)
def _llm_proposal(db: Session, line: BOQLine, edition_id: str) -> LineProposal:
    """Thin tool-use loop against OpenRouter via the OpenAI SDK.

    Model defaults to `google/gemini-2.0-flash-001`; override via OPENROUTER_MODEL.
    Any network / parse / loop-budget error falls back to the deterministic
    path — mapping never blocks the overall run.
    """
    try:
        from openai import OpenAI
    except ImportError:
        return _deterministic_proposal(db, line, edition_id)

    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key or api_key.startswith("sk-or-replace"):
        return _deterministic_proposal(db, line, edition_id)

    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")

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
    system = _load_prompt()
    user_msg = (
        f"BOQ line to map:\n"
        f"- description: {line.description}\n"
        f"- unit: {line.unit}\n"
        f"- element: {line.element}\n"
        f"- edition_id: {edition_id}\n\n"
        f"Call `search_rates` first with query = description. "
        f"Then output ONLY a JSON object with keys top_3 (array of rate_item_id),"
        f" confidence (0-1), reason (one sentence). No prose outside the JSON."
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]
    try:
        for _ in range(5):
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools.TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0.0,
                max_tokens=800,
            )
            msg = resp.choices[0].message
            # Preserve the assistant turn (including any tool_calls) in history.
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    } for tc in (msg.tool_calls or [])
                ] or None,
            })
            if not msg.tool_calls:
                return _parse_llm_output(db, msg.content or "", line)
            for tc in msg.tool_calls:
                try:
                    args = _json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}
                out = tools.dispatch(db, tc.function.name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.function.name,
                    "content": _safe_json(out),
                })
        return _deterministic_proposal(db, line, edition_id)
    except Exception:
        return _deterministic_proposal(db, line, edition_id)


def _parse_llm_output(db: Session, text: str, line: BOQLine) -> LineProposal:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip(), flags=re.MULTILINE)
    try:
        payload = _json.loads(cleaned)
    except Exception:
        # Try to pull the first {...} block out of chatty responses.
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not m:
            return LineProposal(
                boq_line_id=line.id, candidates=[], confidence=0.0,
                reason=f"LLM returned unparseable text: {text[:120]!r}",
                strategy="llm",
            )
        try:
            payload = _json.loads(m.group(0))
        except Exception:
            return LineProposal(
                boq_line_id=line.id, candidates=[], confidence=0.0,
                reason=f"LLM returned unparseable text: {text[:120]!r}",
                strategy="llm",
            )

    ids = payload.get("top_3") or []
    rows = db.query(RateItem).filter(RateItem.id.in_(ids)).all()
    by_id = {r.id: r for r in rows}
    cands: list[Candidate] = []
    for i, iid in enumerate(ids):
        r = by_id.get(iid)
        if r is None:
            continue
        cands.append(Candidate(
            rate_item_id=r.id, item_no=r.item_no, chapter=r.chapter or "",
            description=r.description, unit=r.unit, rate=float(r.rate),
            score=max(0.0, float(payload.get("confidence", 0.0)) * (0.8 ** i)),
        ))
    return LineProposal(
        boq_line_id=line.id,
        candidates=cands,
        confidence=float(payload.get("confidence", 0.0)),
        reason=str(payload.get("reason", "")),
        strategy="llm",
    )


def _safe_json(obj: Any) -> str:
    return _json.dumps(obj, default=str)


def _load_prompt() -> str:
    from pathlib import Path

    return (Path(__file__).parent / "prompts" / "mapping.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------- orchestrator
def _llm_mode_enabled() -> bool:
    """Decide which path the mapper takes.

    Explicit `MAPPING_STRATEGY` env wins:
      - "llm"           → always LLM (requires an OpenRouter key)
      - "deterministic" → always deterministic (batched real embeddings if key is set,
                          pseudo embeddings otherwise)
      - "auto" / unset  → LLM when key is set, deterministic otherwise

    `OPENROUTER_API_KEY` is still used for embeddings even in deterministic
    mode, so Postgres cosine search gets real vectors.
    """
    strategy = os.getenv("MAPPING_STRATEGY", "auto").strip().lower()
    if strategy == "llm":
        return True
    if strategy == "deterministic":
        return False
    # auto
    k = os.getenv("OPENROUTER_API_KEY", "").strip()
    return bool(k) and not k.startswith("sk-or-replace")


def propose_for_line(
    db: Session,
    line: BOQLine,
    edition_id: str,
    *,
    query_vector: np.ndarray | None = None,
) -> LineProposal:
    """Public: single-line entry used by evals and the agent run."""
    if _llm_mode_enabled():
        return _llm_proposal(db, line, edition_id)
    return _deterministic_proposal(db, line, edition_id, query_vector=query_vector)


def apply_mapping(db: Session, line: BOQLine, candidate: Candidate, cost_index: float) -> None:
    """Set the BOQ line's rate_item + rate + amount from a candidate."""
    line.rate_item_id = candidate.rate_item_id
    line.rate = round(candidate.rate * (cost_index or 1.0), 2)
    line.amount = round((line.qty or 0.0) * (line.rate or 0.0), 2)


def map_estimate(
    db: Session,
    estimate: Estimate,
    *,
    edition_id: str,
    org_id: str,
) -> MappingResult:
    """Run the mapper over every BOQ line of an estimate. Returns a summary.

    Blocking (<~90 s on 50 lines in deterministic mode). Agents move to Arq workers
    in W18; HTTP shape stays the same.
    """
    t0 = time.perf_counter()
    strategy = "llm" if _llm_mode_enabled() else "deterministic"
    model_label = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001") if strategy == "llm" else None
    edition = db.query(RateEdition).filter(RateEdition.id == edition_id).one_or_none()
    if edition is None:
        raise ValueError(f"rate edition {edition_id} not found")

    # Clear any leftover pending proposals for this estimate (idempotent).
    db.query(MappingProposal).filter(
        MappingProposal.estimate_id == estimate.id,
        MappingProposal.status == "pending",
    ).delete()

    # Pre-compute every BOQ-line query embedding in a single batched OpenRouter
    # call. Without this the deterministic path makes one embedding round-trip
    # per line (~2s each, 100s+ on a 50-line estimate).
    lines = list(estimate.boq_lines)
    vec_by_line_id: dict[str, np.ndarray] = {}
    if lines and strategy == "deterministic":
        descriptions = [ln.description for ln in lines]
        vecs = list(embed_texts(descriptions))
        for ln, v in zip(lines, vecs, strict=True):
            vec_by_line_id[ln.id] = v

    auto, queued, cache_hits, processed = 0, 0, 0, 0
    cost_index = float(estimate.cost_index or 1.0)
    for line in lines:
        processed += 1
        # 1. Org-cache short-circuit.
        cached = _lookup_org_cache(db, org_id, line, edition_id)
        if cached is not None:
            apply_mapping(db, line, cached, cost_index)
            auto += 1
            cache_hits += 1
            continue
        # 2. Fresh proposal (LLM or deterministic).
        prop = propose_for_line(
            db, line, edition_id,
            query_vector=vec_by_line_id.get(line.id),
        )
        if not prop.candidates:
            queued += 1
            db.add(_proposal_row(estimate.id, prop))
            continue
        if prop.confidence >= AUTO_APPLY_THRESHOLD:
            apply_mapping(db, line, prop.candidates[0], cost_index)
            # Remember so the next estimate skips the LLM for this description.
            _write_org_cache(db, org_id, line, edition_id, prop.candidates[0])
            auto += 1
        else:
            queued += 1
            db.add(_proposal_row(estimate.id, prop))

    # Totals get recomputed by the caller after mapping; here we only touch lines.
    db.commit()

    # Audit row.
    db.add(AgentRun(
        estimate_id=estimate.id,
        agent="mapping",
        model=model_label,
        input={"edition_id": edition_id, "line_count": processed},
        output={
            "auto_applied": auto, "queued": queued,
            "cache_hits": cache_hits, "strategy": strategy,
        },
        status="completed",
        latency_ms=int((time.perf_counter() - t0) * 1000),
    ))
    db.commit()

    return MappingResult(
        estimate_id=estimate.id,
        edition_id=edition_id,
        strategy=strategy,
        processed=processed,
        auto_applied=auto,
        queued=queued,
        cache_hits=cache_hits,
        duration_s=time.perf_counter() - t0,
    )


# ---------------------------------------------------------------- cache + queue
def _lookup_org_cache(
    db: Session, org_id: str, line: BOQLine, edition_id: str,
) -> Candidate | None:
    h = description_hash(line.description, line.unit)
    row = (
        db.query(OrgMapping)
        .filter(
            OrgMapping.org_id == org_id,
            OrgMapping.description_hash == h,
            OrgMapping.edition_id == edition_id,
        )
        .one_or_none()
    )
    if row is None:
        return None
    ri = db.query(RateItem).filter(RateItem.id == row.rate_item_id).one_or_none()
    if ri is None:
        return None
    return Candidate(
        rate_item_id=ri.id, item_no=ri.item_no, chapter=ri.chapter or "",
        description=ri.description, unit=ri.unit, rate=float(ri.rate),
        score=1.0,
    )


def _write_org_cache(
    db: Session, org_id: str, line: BOQLine, edition_id: str, cand: Candidate,
) -> None:
    h = description_hash(line.description, line.unit)
    existing = db.query(OrgMapping).filter_by(
        org_id=org_id, description_hash=h, edition_id=edition_id,
    ).one_or_none()
    if existing is not None:
        existing.rate_item_id = cand.rate_item_id
        existing.accepted_at = datetime.now(UTC)
        return
    db.add(OrgMapping(
        org_id=org_id, edition_id=edition_id, description_hash=h,
        unit=line.unit, rate_item_id=cand.rate_item_id,
    ))


def _proposal_row(estimate_id: str, prop: LineProposal) -> MappingProposal:
    return MappingProposal(
        estimate_id=estimate_id,
        boq_line_id=prop.boq_line_id,
        top_candidates=[c.to_dict() for c in prop.candidates],
        confidence=prop.confidence,
        reason=prop.reason,
        strategy=prop.strategy,
        status="pending",
    )


def accept_proposal(
    db: Session,
    *,
    proposal: MappingProposal,
    rate_item_id: str,
    org_id: str,
    user_id: str | None,
) -> BOQLine:
    """Apply a chosen candidate: update BOQ line, cache, close the proposal."""
    if proposal.status != "pending":
        raise ValueError(f"proposal already {proposal.status}")
    item = db.query(RateItem).filter(RateItem.id == rate_item_id).one_or_none()
    if item is None:
        raise ValueError(f"rate item {rate_item_id} not found")
    # The item MUST be among the stored candidates — guards against UI injection.
    if not any(c["rate_item_id"] == rate_item_id for c in proposal.top_candidates):
        raise ValueError("rate item is not among the stored candidates")

    line = db.query(BOQLine).filter(BOQLine.id == proposal.boq_line_id).one()
    estimate = db.query(Estimate).filter(Estimate.id == proposal.estimate_id).one()

    cand = Candidate(
        rate_item_id=item.id, item_no=item.item_no, chapter=item.chapter or "",
        description=item.description, unit=item.unit, rate=float(item.rate), score=1.0,
    )
    apply_mapping(db, line, cand, float(estimate.cost_index or 1.0))

    proposal.status = "accepted"
    proposal.accepted_rate_item_id = item.id
    proposal.accepted_at = datetime.now(UTC)

    _write_org_cache(db, org_id, line, proposal_edition_id(db, proposal), cand)

    # Recompute totals on the estimate.
    subtotal = round(sum((ln.amount or 0.0) for ln in estimate.boq_lines), 2)
    cont = round(subtotal * (estimate.contingency_pct or 0.0) / 100.0, 2)
    prelim = round(subtotal * (estimate.prelims_pct or 0.0) / 100.0, 2)
    estimate.total_cost = round(subtotal + cont + prelim, 2)
    totals: dict[str, float] = {}
    for ln in estimate.boq_lines:
        totals[ln.element] = round(totals.get(ln.element, 0.0) + (ln.amount or 0.0), 2)
    estimate.totals_by_element = totals

    db.commit()
    return line


def skip_proposal(db: Session, proposal: MappingProposal) -> None:
    proposal.status = "skipped"
    db.commit()


def proposal_edition_id(db: Session, proposal: MappingProposal) -> str:
    """Edition the proposal targets. Derived from the first candidate; falls back to
    the estimate's rate_edition_id."""
    if proposal.top_candidates:
        rate_item = db.query(RateItem).filter(
            RateItem.id == proposal.top_candidates[0]["rate_item_id"]
        ).one_or_none()
        if rate_item is not None:
            return rate_item.edition_id
    est = db.query(Estimate).filter(Estimate.id == proposal.estimate_id).one()
    return est.rate_edition_id or ""
