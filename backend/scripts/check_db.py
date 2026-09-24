"""Check the database at DATABASE_URL is ready: create tables, seed if empty, run sample 01.

    python scripts/check_db.py
    DATABASE_URL='postgresql+psycopg://USER:PASSWORD@HOST/DB?sslmode=require' python scripts/check_db.py

Works on SQLite and Postgres. Unlike run_cli.py this writes to the real database,
so sample 01 appears in the ledger like a run from the UI. Uses the cached extraction
in fixtures/extractions/, so it makes no LLM calls.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.config import BACKEND_DIR  # noqa: E402
from app.db import SessionLocal, engine, init_db  # noqa: E402
from app.models import Invoice, PurchaseOrder, Vendor  # noqa: E402
from app.pipeline.runner import create_run, run_pipeline  # noqa: E402
from app.seed import seed_if_empty  # noqa: E402

SAMPLE = BACKEND_DIR / "samples" / "01_happy_deccan.pdf"
EXPECTED = "Approve"


def main() -> int:
    print(f"Database: {engine.url.render_as_string(hide_password=True)} ({engine.dialect.name})")
    init_db()
    print("Tables: ok")

    with SessionLocal() as db:
        seeded = seed_if_empty(db)
        counts = {m.__tablename__: db.scalar(select(func.count()).select_from(m)) for m in (Vendor, PurchaseOrder, Invoice)}
        print(f"Seed: {'loaded now' if seeded else 'already present'} · " + ", ".join(f"{k}={v}" for k, v in counts.items()))

        ctx = create_run(db, SAMPLE.read_bytes(), SAMPLE.name, store_file=True)
        run_pipeline(ctx, min_stage_ms=0)
        row = db.get(Invoice, ctx.run_id)
        print(f"Run {ctx.run_id} on {SAMPLE.name}: decision={ctx.decision}, status={row.status}, "
              f"LLM calls={ctx.llm_calls}")
        for f in ctx.findings:
            print(f"  [{f.label} {f.severity}] {f.message}")

    if ctx.decision is None or row.status == "running":
        print("FAILED: the run did not reach a decision.")
        return 1
    if ctx.decision != EXPECTED:
        # Expected after the first check: sample 01 is already in the ledger, so stage 7 flags it.
        print(f"Note: sample 01 alone gives {EXPECTED}; a repeat run on the same database is a duplicate.")
    print("OK: database ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
