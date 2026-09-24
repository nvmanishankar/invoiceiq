"""The in-app test suite (build guide section 17): every sample, expected vs actual, on a scratch database.

Runs against a fresh in-memory SQLite copy of the seed data, never the live database, so it can't touch live runs,
alerts, POs, settings or the daily cap. Offline: committed caches only, no Gemini calls, no emails.
Codes in expected.json are "must include", not "only these" (docs/SEED_KIT_README.md).
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import llm, seed
from app.db import make_engine
from app.models import RunStage
from app.pipeline.runner import create_run, file_hash, run_pipeline
from app.services import runs as run_service

log = logging.getLogger(__name__)

COOLDOWN_SECONDS = 10
NO_CACHE = "No cached extraction for this sample"

_lock = threading.Lock()
_last_finished: float | None = None


class SuiteBusy(Exception):
    pass


class SuiteCoolingDown(Exception):
    def __init__(self, wait: int):
        super().__init__(f"The test suite has just run. Please wait {wait} s before running it again.")
        self.wait = wait


def expected_samples() -> list[dict]:
    return json.loads((run_service.SAMPLES_DIR / "expected.json").read_text(encoding="utf-8"))


def _unique(codes: list[str]) -> list[str]:
    return list(dict.fromkeys(codes))


def _row(exp: dict) -> dict:
    """A result row before running: what expected.json says, nothing actual yet."""
    return {
        "file": exp["file"],
        "story": exp.get("story"),
        "expected_decision": exp["decision"],
        "actual_decision": None,
        "expected_codes": exp["codes"],
        "actual_codes": [],
        "missing_codes": list(exp["codes"]),
        "passed": False,
        "expected_po_id": exp.get("po_id"),
        "actual_po_id": None,
        "expected_due_date": exp.get("due_date"),
        "actual_due_date": None,
        "llm_calls": 0,
        "duration_ms": 0,
        "error": None,
        "stages": [],
    }


def run_one(db: Session, exp: dict) -> dict:
    """Run one sample on the scratch database. Never raises: a problem is a failed row with an error."""
    out = _row(exp)
    path = run_service.SAMPLES_DIR / exp["file"]
    t0 = time.monotonic()
    try:
        if not path.is_file():
            out["error"] = "The sample file is missing"
            return out
        data = path.read_bytes()
        if llm.load_cache(file_hash(data)) is None:  # never spend quota: no cache, no run
            out["error"] = NO_CACHE
            return out
        ctx = create_run(db, data, exp["file"], today=run_service.today())
        ctx.offline, ctx.send_emails = True, False
        run_pipeline(ctx, min_stage_ms=0)
        codes = _unique(ctx.codes())
        stages = db.scalars(select(RunStage).where(RunStage.run_id == ctx.run_id).order_by(RunStage.stage_order)).all()
        out.update(
            actual_decision=ctx.decision,
            actual_codes=codes,
            missing_codes=[c for c in exp["codes"] if c not in codes],
            actual_po_id=ctx.po.po_id if ctx.po else None,
            actual_due_date=ctx.due_date.isoformat() if ctx.due_date else None,
            llm_calls=ctx.llm_calls,
            stages=[{"name": s.stage_name, "status": s.status, "message": s.message} for s in stages],
        )
        out["passed"] = ctx.decision == exp["decision"] and not out["missing_codes"]
    except Exception as e:  # one broken sample must not stop the suite
        log.exception("test suite: %s failed", exp["file"])
        db.rollback()
        out["error"] = f"The run stopped: {type(e).__name__}"
    finally:
        out["duration_ms"] = int((time.monotonic() - t0) * 1000)
    return out


def run_suite() -> dict:
    """Every sample in expected.json order on one fresh scratch database. One suite at a time, then a cool-down."""
    global _last_finished
    if not _lock.acquire(blocking=False):
        raise SuiteBusy("The test suite is already running. Wait for it to finish, then look at its results.")
    try:
        if _last_finished is not None:
            wait = COOLDOWN_SECONDS - (time.monotonic() - _last_finished)
            if wait > 0:
                raise SuiteCoolingDown(max(1, round(wait)))
        ran_at = datetime.now(timezone.utc)
        t0 = time.monotonic()
        engine = make_engine("sqlite://")  # in memory; one connection per thread, and this all runs in one thread
        try:
            seed.reset(engine)
            with Session(engine, autoflush=False, expire_on_commit=False) as db:
                results = [run_one(db, exp) for exp in expected_samples()]
        finally:
            engine.dispose()
        _last_finished = time.monotonic()
        return {
            "passed": sum(r["passed"] for r in results),
            "total": len(results),
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "ran_at": ran_at.isoformat(timespec="seconds"),
            "results": results,
        }
    finally:
        _lock.release()
