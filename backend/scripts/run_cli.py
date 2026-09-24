"""Run the pipeline on PDFs from the terminal.

    python scripts/run_cli.py samples/01_happy_deccan.pdf
    python scripts/run_cli.py samples/*.pdf --fields

By default each run uses a fresh in-memory database seeded with the demo data,
so the local ledger isn't touched. Pass --persist to write to DATABASE_URL.
Extractions are cached in fixtures/extractions/ by file hash.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from app.db import SessionLocal, init_db, make_engine  # noqa: E402
from app.pipeline.runner import create_run, run_pipeline  # noqa: E402
from app.seed import reset, seed_if_empty  # noqa: E402

ICONS = {"pass": "✔", "warn": "!", "fail": "✘", "info": "i"}


def print_stage(order, name, result):
    print(f"  {order:>2}. {ICONS.get(result.status, '?')} {name:<24} {result.message}")


def run_file(path: Path, db: Session, show_fields: bool) -> None:
    print(f"\n{path.name}")
    ctx = create_run(db, path.read_bytes(), path.name)
    run_pipeline(ctx, min_stage_ms=0, on_stage=print_stage)
    for f in ctx.findings:
        to = ", ".join(f.audience) or "—"
        print(f"      [{f.code} {f.severity}] {f.message}  (to: {to})")
    print(f"      LLM calls this run: {ctx.llm_calls}")
    if show_fields and ctx.extraction:
        print(json.dumps(ctx.extraction, indent=2, ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--fields", action="store_true", help="print the extracted fields as JSON")
    ap.add_argument("--persist", action="store_true", help="write runs to DATABASE_URL instead of a throwaway DB")
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING, format="      %(levelname)s %(name)s: %(message)s")

    for path in args.files:
        if args.persist:
            init_db()
            with SessionLocal() as db:
                seed_if_empty(db)
                run_file(path, db, args.fields)
        else:
            eng = make_engine("sqlite://")
            reset(eng)
            with Session(eng) as db:
                run_file(path, db, args.fields)
            eng.dispose()


if __name__ == "__main__":
    main()
