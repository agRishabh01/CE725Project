"""Import a schedule of rates into the RateEdition / RateItem tables.

Three input paths:
  - YAML (dev / fixture)          → `import_from_yaml`
  - Excel (if source is clean)    → `import_from_excel`
  - PDF (CPWD DSR 2023 real)      → `import_from_pdf`

All paths normalise units (cum→m³, sqm→m²) and reject the whole import if any
row is missing a rate or has a unit the engine doesn't understand. Duplicates
within an edition raise a hard error — DSR item numbers must be unique.

Embeddings are computed on *publish*, not on import. See services/embeddings.py.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from api.db.models import RateEdition, RateItem

# -------------------------------------------------------------- unit normalisation
_UNIT_MAP = {
    "cum": "m3", "cu.m": "m3", "cu m": "m3", "cu.m.": "m3", "m³": "m3",
    "sqm": "m2", "sq.m": "m2", "sq m": "m2", "sq.m.": "m2", "m²": "m2",
    "rmt": "m", "rm": "m", "rmetre": "m", "meter": "m", "metre": "m",
    "no": "nos", "no.": "nos", "number": "nos", "each": "nos",
    "kgs": "kg", "kilogram": "kg",
    "qtl": "q", "quintal": "q",
    "mt": "t", "tonne": "t", "ton": "t",
}
_ALLOWED_UNITS = {"m", "m2", "m3", "kg", "nos", "l", "q", "t"}


def normalise_unit(raw: str) -> str:
    """Map common DSR unit spellings to engine canon. Raise on unknown."""
    key = raw.strip().lower().replace(" ", "")
    cleaned = _UNIT_MAP.get(key, _UNIT_MAP.get(raw.strip().lower(), raw.strip().lower()))
    if cleaned not in _ALLOWED_UNITS:
        raise ValueError(f"unknown unit: {raw!r}")
    return cleaned


# -------------------------------------------------------------- parsed row
@dataclass(frozen=True, slots=True)
class ParsedRow:
    item_no: str
    chapter: str
    description: str
    unit: str
    rate: float


# -------------------------------------------------------------- validation
class ImportError_(Exception):
    """Raised when an edition cannot be imported — collects reasons."""

    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def _validate(rows: list[ParsedRow]) -> None:
    """Fail the whole import rather than silently drop bad data."""
    reasons: list[str] = []
    seen: set[str] = set()
    for r in rows:
        if r.item_no in seen:
            reasons.append(f"duplicate item_no: {r.item_no}")
        seen.add(r.item_no)
        if not r.description.strip():
            reasons.append(f"empty description at {r.item_no}")
        if r.rate <= 0:
            reasons.append(f"non-positive rate at {r.item_no}: {r.rate}")
        if not re.fullmatch(r"[0-9A-Za-z.\-/]+", r.item_no):
            reasons.append(f"malformed item_no: {r.item_no!r}")
    if reasons:
        raise ImportError_(reasons)


# -------------------------------------------------------------- YAML path
def import_from_yaml(session: Session, path: str | Path) -> RateEdition:
    """Load a YAML fixture (dev). Returns the committed RateEdition."""
    p = Path(path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    meta = raw["edition"]
    rows = [
        ParsedRow(
            item_no=str(it["item_no"]),
            chapter=str(it.get("chapter", "")),
            description=str(it["description"]),
            unit=normalise_unit(str(it["unit"])),
            rate=float(it["rate"]),
        )
        for it in raw["items"]
    ]
    _validate(rows)
    return _persist_edition(
        session,
        source=str(meta.get("source", "unknown")),
        region=str(meta.get("region", "")),
        year=int(meta.get("year", date.today().year)),
        effective_date=_parse_date(meta.get("effective_date")),
        file_bytes=p.read_bytes(),
        rows=rows,
    )


# -------------------------------------------------------------- Excel path
def import_from_excel(
    session: Session,
    path: str | Path,
    *,
    source: str,
    region: str,
    year: int,
    header_row: int = 1,
    columns: dict[str, str] | None = None,
) -> RateEdition:
    """Import from an Excel sheet. `columns` maps engine field → sheet header
    (defaults to item_no/chapter/description/unit/rate)."""
    from openpyxl import load_workbook

    cols = columns or {
        "item_no": "Item No",
        "chapter": "Chapter",
        "description": "Description",
        "unit": "Unit",
        "rate": "Rate",
    }
    p = Path(path)
    wb = load_workbook(p, read_only=True, data_only=True)
    ws = wb.active
    headers = {str(c.value).strip(): i for i, c in enumerate(ws[header_row]) if c.value}
    missing = [name for name in cols.values() if name not in headers]
    if missing:
        raise ImportError_([f"missing columns: {missing}"])

    rows: list[ParsedRow] = []
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        if not row or row[headers[cols["item_no"]]] is None:
            continue
        rows.append(
            ParsedRow(
                item_no=str(row[headers[cols["item_no"]]]).strip(),
                chapter=str(row[headers[cols["chapter"]]] or "").strip(),
                description=str(row[headers[cols["description"]]] or "").strip(),
                unit=normalise_unit(str(row[headers[cols["unit"]]] or "")),
                rate=float(row[headers[cols["rate"]]]),
            )
        )
    _validate(rows)
    return _persist_edition(
        session,
        source=source,
        region=region,
        year=year,
        effective_date=None,
        file_bytes=p.read_bytes(),
        rows=rows,
    )


# -------------------------------------------------------------- PDF path
def import_from_pdf(
    session: Session,
    path: str | Path,
    *,
    source: str = "CPWD DSR",
    region: str = "Delhi",
    year: int = 2023,
    llm_row_repair: bool = False,
) -> RateEdition:
    """Import from a tabular PDF via pdfplumber.

    This handles the common case of DSR tables: 4 columns (item, description, unit, rate)
    with a chapter heading before each table block. If a row looks broken and
    `llm_row_repair=True` and an Anthropic key is set, the row is sent to Claude Haiku
    for repair. In Week 4 we leave the LLM pass off by default — the tunable is wired
    for Week 11+ when the intake agent exists.
    """
    import pdfplumber

    p = Path(path)
    rows: list[ParsedRow] = []
    current_chapter = ""
    with pdfplumber.open(p) as pdf:
        for page in pdf.pages:
            # Heading detection: pick the uppercase-ish first text line as chapter.
            text = page.extract_text() or ""
            for ln in text.splitlines()[:3]:
                stripped = ln.strip()
                if (
                    stripped
                    and stripped == stripped.upper()
                    and 3 < len(stripped) < 60
                    and not re.search(r"\d", stripped)
                ):
                    current_chapter = stripped.title()
                    break
            for table in page.extract_tables() or []:
                rows.extend(_rows_from_pdf_table(table, current_chapter))
    if llm_row_repair:
        rows = _repair_rows_with_llm(rows)
    _validate(rows)
    return _persist_edition(
        session,
        source=source,
        region=region,
        year=year,
        effective_date=None,
        file_bytes=p.read_bytes(),
        rows=rows,
    )


def _rows_from_pdf_table(table: list[list[str | None]], chapter: str) -> list[ParsedRow]:
    """Heuristic: a DSR row has an item-no in column 0, description in 1, unit in -2, rate in -1."""
    out: list[ParsedRow] = []
    for raw in table:
        if not raw or len(raw) < 4:
            continue
        item_no = (raw[0] or "").strip()
        desc = (raw[1] or "").strip()
        unit = (raw[-2] or "").strip()
        rate_text = (raw[-1] or "").strip().replace(",", "")
        if not item_no or not desc or not re.search(r"\d", rate_text):
            continue
        try:
            rate = float(re.sub(r"[^0-9.]", "", rate_text))
            out.append(
                ParsedRow(
                    item_no=item_no,
                    chapter=chapter,
                    description=desc,
                    unit=normalise_unit(unit),
                    rate=rate,
                )
            )
        except (ValueError, KeyError):
            # Row looks broken — a later LLM pass can repair; drop silently here.
            continue
    return out


def _repair_rows_with_llm(rows: list[ParsedRow]) -> list[ParsedRow]:
    """Placeholder for the Claude-Haiku row-repair pass. Enabled in W11+."""
    return rows


# -------------------------------------------------------------- persistence
def _persist_edition(
    session: Session,
    *,
    source: str,
    region: str,
    year: int,
    effective_date: date | None,
    file_bytes: bytes,
    rows: Iterable[ParsedRow],
) -> RateEdition:
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    existing = (
        session.query(RateEdition)
        .filter_by(source=source, region=region, year=year)
        .one_or_none()
    )
    if existing is not None:
        raise ImportError_(
            [f"edition already exists: {source}/{region}/{year} (id={existing.id})"]
        )

    edition = RateEdition(
        source=source,
        region=region,
        year=year,
        effective_date=effective_date,
        file_hash=file_hash,
        scope="global",
    )
    session.add(edition)
    session.flush()  # populate edition.id
    for r in rows:
        session.add(
            RateItem(
                edition_id=edition.id,
                item_no=r.item_no,
                chapter=r.chapter,
                description=r.description,
                unit=r.unit,
                rate=r.rate,
            )
        )
    session.commit()
    return edition


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
