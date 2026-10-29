"""DSR-style xlsx export.

Layout:
  Row 1-5   : header block (project, estimate, date, rate edition, watermark)
  Row 7     : column headings (Serial | DSR Item No | Description | Unit | Qty | Rate | Amount)
  Row 8..n  : element-grouped line items with per-element subtotals
  Row n+2.. : totals block (subtotal, cost index, contingency %, prelims %, grand total)

Grand total matches `Estimate.total_cost` to the paisa — the W9 "done when"
contract. The spreadsheet is self-sufficient: anyone opening it can verify the
total from the printed line amounts without the app.
"""
from __future__ import annotations

import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from sqlalchemy.orm import Session

from api.db.models import Estimate, Project, RateEdition, RateItem

# --------------------------------------------------------------- styles
_HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
_HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
_TITLE_FONT = Font(bold=True, size=14)
_META_LABEL_FONT = Font(bold=True, color="595959", size=9)
_META_VALUE_FONT = Font(size=10)
_ELEM_FONT = Font(bold=True, color="1F4E78", size=10)
_ELEM_FILL = PatternFill("solid", fgColor="D9E1F2")
_SUBTOTAL_FONT = Font(bold=True, italic=True)
_SUBTOTAL_FILL = PatternFill("solid", fgColor="F2F2F2")
_TOTAL_FONT = Font(bold=True, size=12)
_TOTAL_FILL = PatternFill("solid", fgColor="FFF2CC")
_GRAND_FILL = PatternFill("solid", fgColor="FFE699")
_OVERRIDE_FILL = PatternFill("solid", fgColor="FFF2CC")

_INR_FMT = '#,##0.00;[Red]-#,##0.00'
_QTY_FMT = "#,##0.000"
_BORDER = Border(
    left=Side(style="thin", color="BFBFBF"),
    right=Side(style="thin", color="BFBFBF"),
    top=Side(style="thin", color="BFBFBF"),
    bottom=Side(style="thin", color="BFBFBF"),
)

_HEADINGS = ["Serial", "DSR Item No", "Description", "Unit", "Qty", "Rate (INR)", "Amount (INR)"]
_WIDTHS = [8, 14, 70, 8, 12, 14, 16]
_WATERMARK = "PRELIMINARY · AACE Class 4/5 · engine-computed, not a tender"


# ---------------------------------------------------------- public entrypoint
def estimate_to_xlsx(estimate: Estimate, db: Session | None = None) -> bytes:
    """Serialise an Estimate (and its BOQ lines) to a .xlsx byte blob.

    If a Session is passed, we hydrate the DSR item_no for lines that have a
    `rate_item_id` set. Without one, the DSR column stays empty — the file is
    still valid, just less annotated.
    """
    wb = Workbook()
    ws: Worksheet = wb.active
    ws.title = "BOQ Abstract"

    item_no_by_id = _hydrate_item_nos(db, estimate) if db else {}
    project_name, edition_label = _hydrate_meta(db, estimate) if db else (None, None)

    _write_header_block(ws, estimate, project_name, edition_label)
    row = _write_column_headings(ws, start_row=7)
    row, element_rows = _write_line_items(ws, estimate, item_no_by_id, start_row=row)
    _write_totals_block(ws, estimate, start_row=row + 1)

    _apply_column_widths(ws)
    ws.freeze_panes = "A8"
    ws.print_options.gridLines = False

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------- header block
def _write_header_block(
    ws: Worksheet,
    estimate: Estimate,
    project_name: str | None,
    edition_label: str | None,
) -> None:
    ws["A1"] = f"BOQ Abstract — {project_name or 'Estimate'}"
    ws["A1"].font = _TITLE_FONT
    ws.merge_cells("A1:G1")

    meta = [
        ("Estimate ID", estimate.id),
        ("Status", (estimate.status or "draft").title()),
        ("Rate edition", edition_label or "—"),
        ("Cost index", f"{estimate.cost_index:.3f}"),
        ("Generated", datetime.now().strftime("%d %b %Y, %H:%M")),
    ]
    for i, (label, value) in enumerate(meta):
        r = 3 + (i // 2)
        c = 1 + (i % 2) * 3  # column A or D
        ws.cell(row=r, column=c, value=label).font = _META_LABEL_FONT
        ws.cell(row=r, column=c + 1, value=value).font = _META_VALUE_FONT

    ws.cell(row=6, column=1, value=_WATERMARK).font = Font(italic=True, color="C00000", size=9)
    ws.merge_cells(start_row=6, start_column=1, end_row=6, end_column=7)


# ---------------------------------------------------------- column headings
def _write_column_headings(ws: Worksheet, start_row: int) -> int:
    for i, label in enumerate(_HEADINGS, start=1):
        c = ws.cell(row=start_row, column=i, value=label)
        c.font = _HEADER_FONT
        c.fill = _HEADER_FILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = _BORDER
    ws.row_dimensions[start_row].height = 30
    return start_row + 1


# ---------------------------------------------------------- line items
def _write_line_items(
    ws: Worksheet,
    estimate: Estimate,
    item_no_by_id: dict[str, str],
    start_row: int,
) -> tuple[int, dict[str, int]]:
    lines = sorted(estimate.boq_lines, key=lambda ln: (ln.element, ln.seq))
    row = start_row
    serial = 1
    current_element: str | None = None
    element_subtotal_rows: dict[str, int] = {}
    element_start_row: int | None = None
    element_running: float = 0.0

    for ln in lines:
        if ln.element != current_element:
            # Close prior element
            if current_element is not None and element_start_row is not None:
                row = _write_element_subtotal(ws, row, current_element, element_running)
                element_subtotal_rows[current_element] = row
                row += 1
            # Open new element
            current_element = ln.element
            element_start_row = row
            element_running = 0.0
            ws.cell(row=row, column=1, value=ln.element.upper().replace("_", " ")).font = _ELEM_FONT
            for col in range(1, len(_HEADINGS) + 1):
                ws.cell(row=row, column=col).fill = _ELEM_FILL
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=7)
            row += 1

        amount = ln.amount or 0.0
        _write_data_row(
            ws, row,
            serial=serial,
            item_no=item_no_by_id.get(ln.rate_item_id or "", ""),
            description=ln.description,
            unit=ln.unit,
            qty=ln.qty or 0.0,
            rate=ln.rate or 0.0,
            amount=amount,
            overridden=bool(ln.is_overridden),
        )
        element_running += amount
        serial += 1
        row += 1

    if current_element is not None:
        row = _write_element_subtotal(ws, row, current_element, element_running)
        element_subtotal_rows[current_element] = row
        row += 1

    return row, element_subtotal_rows


def _write_data_row(
    ws: Worksheet,
    row: int,
    *,
    serial: int,
    item_no: str,
    description: str,
    unit: str,
    qty: float,
    rate: float,
    amount: float,
    overridden: bool,
) -> None:
    ws.cell(row=row, column=1, value=serial).alignment = Alignment(horizontal="center")
    ws.cell(row=row, column=2, value=item_no or "").alignment = Alignment(horizontal="center")
    ws.cell(row=row, column=3, value=description).alignment = Alignment(wrap_text=True, vertical="top")
    ws.cell(row=row, column=4, value=unit).alignment = Alignment(horizontal="center")
    ws.cell(row=row, column=5, value=qty).number_format = _QTY_FMT
    ws.cell(row=row, column=6, value=rate).number_format = _INR_FMT
    ws.cell(row=row, column=7, value=amount).number_format = _INR_FMT
    for col in range(1, 8):
        ws.cell(row=row, column=col).border = _BORDER
        if overridden:
            ws.cell(row=row, column=col).fill = _OVERRIDE_FILL
    if overridden:
        ws.cell(row=row, column=3).comment = _override_comment()


def _write_element_subtotal(ws: Worksheet, row: int, element: str, total: float) -> int:
    label = f"Subtotal — {element.replace('_', ' ')}"
    ws.cell(row=row, column=3, value=label).alignment = Alignment(horizontal="right")
    ws.cell(row=row, column=7, value=round(total, 2))
    for col in range(1, 8):
        c = ws.cell(row=row, column=col)
        c.fill = _SUBTOTAL_FILL
        c.font = _SUBTOTAL_FONT
        c.border = _BORDER
    ws.cell(row=row, column=7).number_format = _INR_FMT
    return row


# ---------------------------------------------------------- totals block
def _write_totals_block(ws: Worksheet, estimate: Estimate, start_row: int) -> None:
    subtotal = round(sum((ln.amount or 0.0) for ln in estimate.boq_lines), 2)
    cont_pct = float(estimate.contingency_pct or 0.0)
    prelim_pct = float(estimate.prelims_pct or 0.0)
    contingency = round(subtotal * cont_pct / 100.0, 2)
    prelims = round(subtotal * prelim_pct / 100.0, 2)
    grand = round(estimate.total_cost or (subtotal + contingency + prelims), 2)

    rows = [
        ("Subtotal (civil works)", subtotal, None, _TOTAL_FILL),
        (f"Add contingency @ {cont_pct:.1f}%", contingency, None, _TOTAL_FILL),
        (f"Add preliminaries / overheads @ {prelim_pct:.1f}%", prelims, None, _TOTAL_FILL),
        ("GRAND TOTAL (INR)", grand, _TOTAL_FONT, _GRAND_FILL),
    ]
    row = start_row
    for label, amount, font_override, fill in rows:
        ws.cell(row=row, column=3, value=label).alignment = Alignment(horizontal="right")
        ws.cell(row=row, column=7, value=amount).number_format = _INR_FMT
        for col in range(1, 8):
            c = ws.cell(row=row, column=col)
            c.fill = fill
            c.border = _BORDER
            c.font = font_override or Font(bold=True)
        row += 1

    ws.cell(row=row + 1, column=3, value=_WATERMARK).font = Font(italic=True, color="C00000", size=9)


# ---------------------------------------------------------- helpers
def _apply_column_widths(ws: Worksheet) -> None:
    for i, w in enumerate(_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _override_comment():
    from openpyxl.comments import Comment

    return Comment("Overridden by user — see override_reason", "CE 725 BOQ")


def _hydrate_item_nos(db: Session, estimate: Estimate) -> dict[str, str]:
    ids = [ln.rate_item_id for ln in estimate.boq_lines if ln.rate_item_id]
    if not ids:
        return {}
    rows = db.query(RateItem.id, RateItem.item_no).filter(RateItem.id.in_(ids)).all()
    return {rid: no for rid, no in rows}


def _hydrate_meta(db: Session, estimate: Estimate) -> tuple[str | None, str | None]:
    proj = db.query(Project).filter(Project.id == estimate.project_id).one_or_none()
    name = proj.name if proj else None

    label = None
    if estimate.rate_edition_id:
        ed = db.query(RateEdition).filter(RateEdition.id == estimate.rate_edition_id).one_or_none()
        if ed is not None:
            label = f"{ed.source} {ed.region or ''} {ed.year}".strip()
    return name, label
