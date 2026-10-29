"""Operator CLI. Run as `python -m api.cli <subcommand>`.

Subcommands:
  import-dsr <path>                 Import a schedule of rates (yaml|xlsx|pdf by extension)
  search-rates <query> [--limit N]  Try a hybrid rate-item search
  embed <edition_id>                Compute + store embeddings for one edition
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from api.db.session import SessionLocal
from api.services.rate_import import (
    ImportError_,
    import_from_excel,
    import_from_pdf,
    import_from_yaml,
)
from api.services.rate_search import (
    compute_and_store_embeddings,
    ensure_fts_index,
    search_rates,
)


def cmd_import_dsr(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 2
    ext = path.suffix.lower()
    session = SessionLocal()
    try:
        if ext in {".yaml", ".yml"}:
            edition = import_from_yaml(session, path)
        elif ext in {".xlsx", ".xlsm"}:
            edition = import_from_excel(
                session, path, source=args.source, region=args.region, year=args.year,
            )
        elif ext == ".pdf":
            edition = import_from_pdf(
                session, path, source=args.source, region=args.region, year=args.year,
                llm_row_repair=args.repair,
            )
        else:
            print(f"error: unsupported extension {ext}", file=sys.stderr)
            return 2
    except ImportError_ as e:
        print(f"import failed:\n  - " + "\n  - ".join(e.reasons), file=sys.stderr)
        return 1

    ensure_fts_index(session)
    added = compute_and_store_embeddings(session, edition.id)
    print(
        f"imported: {edition.source}/{edition.region}/{edition.year} "
        f"id={edition.id} items={len(edition.items)} embeddings_computed={added}"
    )
    return 0


def cmd_search_rates(args: argparse.Namespace) -> int:
    session = SessionLocal()
    ensure_fts_index(session)
    hits = search_rates(
        session,
        query=args.query,
        edition_id=args.edition,
        unit=args.unit,
        chapter=args.chapter,
        limit=args.limit,
    )
    if not hits:
        print("(no results)")
        return 0
    for h in hits:
        print(
            f"[{h.combined_score:>5.2f}] {h.item_no:>8} {h.unit:>4} "
            f"INR {h.rate:>9.2f}  {h.description[:80]}"
        )
    return 0


def cmd_embed(args: argparse.Namespace) -> int:
    session = SessionLocal()
    n = compute_and_store_embeddings(session, args.edition)
    print(f"computed embeddings for {n} items in edition {args.edition}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    from api.services.validation import list_cases, load_case, run_all, run_case

    paths = []
    if args.cases:
        all_paths = list_cases()
        for c in args.cases:
            match = next((p for p in all_paths if c in p.name), None)
            if match is None:
                print(f"error: no reference matching {c!r}", file=sys.stderr)
                return 2
            paths.append(match)
    report = run_all(paths or None)

    verdict = "PASS" if report.passed else "FAIL"
    print(f"=== Gate 2 verdict: {verdict} ===")
    print(f"median total variance    : {report.median_total_abs_pct}%  (target <= 20%)")
    print(f"median element-weighted  : {report.median_element_weighted_pct}%  (target <= 20%)")
    print(f"calibration <= +/-20%    : {report.all_calibration_within_20}")
    print(f"held-out    <= +/-25%    : {report.all_held_out_within_25}")
    print()
    for c in report.cases:
        marker = "[ok]" if c.pass_total and c.pass_element else "[!!]"
        print(f"  {marker} [{c.split:<11}] {c.case_id}")
        print(f"      expected INR {c.expected_total_inr:>14,.0f}  "
              f"({c.cost_per_m2_expected:>7,.0f}/m2)")
        print(f"      computed INR {c.computed_total_inr:>14,.0f}  "
              f"({c.cost_per_m2_computed:>7,.0f}/m2)")
        print(f"      total delta: {c.total_delta_pct:+.2f}%   "
              f"element weighted err: {c.element_weighted_abs_error_pct}%")
        if args.verbose:
            for e in sorted(c.element_variance, key=lambda x: -abs(x.delta_pct)):
                print(f"        {e.element:<18} expected {e.expected_inr:>12,.0f}  "
                      f"computed {e.computed_inr:>12,.0f}  ({e.delta_pct:+.1f}%)")
        print()
    return 0 if report.passed else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m api.cli")
    sub = p.add_subparsers(dest="cmd", required=True)

    imp = sub.add_parser("import-dsr", help="import a schedule of rates")
    imp.add_argument("path", help="path to .yaml/.xlsx/.pdf")
    imp.add_argument("--source", default="CPWD DSR")
    imp.add_argument("--region", default="Delhi")
    imp.add_argument("--year", type=int, default=2023)
    imp.add_argument("--repair", action="store_true",
                     help="run LLM row-repair pass (W11+)")
    imp.set_defaults(func=cmd_import_dsr)

    s = sub.add_parser("search-rates", help="hybrid search in a rate edition")
    s.add_argument("query")
    s.add_argument("--edition", required=True, help="rate edition id")
    s.add_argument("--unit")
    s.add_argument("--chapter")
    s.add_argument("--limit", type=int, default=10)
    s.set_defaults(func=cmd_search_rates)

    e = sub.add_parser("embed", help="compute embeddings for a rate edition")
    e.add_argument("--edition", required=True)
    e.set_defaults(func=cmd_embed)

    v = sub.add_parser("validate", help="run Gate 2 reference validation")
    v.add_argument("cases", nargs="*", help="filter by substring; empty = all cases")
    v.add_argument("-v", "--verbose", action="store_true",
                   help="show every element's variance, not just worst")
    v.set_defaults(func=cmd_validate)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
