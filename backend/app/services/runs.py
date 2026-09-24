"""Starting runs from the API and finishing them in the background (build guide sections 2 and 12)."""

import json
import logging
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR, settings
from app.db import SessionLocal
from app.models import Invoice, RunStage, utcnow
from app.pipeline import decide
from app.pipeline.context import SYSTEM_ERROR
from app.pipeline.runner import DECISION_ORDER, create_run, load_run, resume_context, run_pipeline

log = logging.getLogger(__name__)

SAMPLES_DIR = BACKEND_DIR / "samples"
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


class DailyCapReached(Exception):
    pass


def today() -> date:
    """The business date for date rules. Tests pin it."""
    return date.today()


def sample_names() -> list[str]:
    return sorted(p.name for p in SAMPLES_DIR.glob("*.pdf"))


def samples() -> list[dict]:
    expected = json.loads((SAMPLES_DIR / "expected.json").read_text(encoding="utf-8"))
    on_disk = set(sample_names())
    return [
        {
            "file": e["file"],
            "story": e["story"],
            "expected_decision": e["decision"],
            "expected_codes": e["codes"],
            "invoice_no": e.get("invoice_no"),
            "vendor_id": e.get("vendor_id"),
            "total_paise": e.get("total_paise"),
            "scanned": e.get("scanned", False),
        }
        for e in expected if e["file"] in on_disk
    ]


def runs_today(db: Session) -> int:
    """Non-seed runs created since midnight UTC."""
    midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return db.scalar(select(func.count()).select_from(Invoice).where(
        Invoice.is_seed.is_(False), Invoice.created_at >= midnight))


def start_run(file_bytes: bytes, file_name: str | None) -> str:
    """Create the invoices row and store the PDF. The pipeline runs later in execute_run."""
    with SessionLocal() as db:
        if runs_today(db) >= settings.MAX_RUNS_PER_DAY:
            raise DailyCapReached(
                f"This demo processes up to {settings.MAX_RUNS_PER_DAY} invoices a day and today's "
                "limit has been reached. Please try again tomorrow, or open an earlier run from the dashboard."
            )
        ctx = create_run(db, file_bytes, file_name, today=today(), store_file=True)
        return ctx.run_id


def execute_run(run_id: str) -> None:
    """Background task: its own session, never the request's. Never leaves a run stuck on 'running'."""
    with SessionLocal() as db:
        try:
            run_pipeline(load_run(db, run_id, today=today()))
        except Exception:
            log.exception("run %s failed outside the stages", run_id)
            db.rollback()
            fail_run(db, run_id, "The system stopped while checking this invoice, so a person needs to review it.")


def resume_run(run_id: str, start_at: int) -> None:
    """Background task after a review: run the stages from `start_at` again, then decide. Same safety as execute_run."""
    with SessionLocal() as db:
        try:
            run_pipeline(resume_context(db, run_id, start_at, today=today()), start_at=start_at)
        except Exception:
            log.exception("resuming run %s failed outside the stages", run_id)
            db.rollback()
            fail_run(db, run_id, "The system stopped while re-checking this invoice after review, so a person "
                                 "needs to review it again.")


def fail_run(db: Session, run_id: str, message: str) -> None:
    """Close a run that couldn't finish: Hold with a system finding and a Decision stage."""
    row = db.get(Invoice, run_id)
    if row is None or row.status != "running":
        return
    finding = {"code": SYSTEM_ERROR, "label": "System error", "severity": "hold", "message": message,
               "audience": ["AP"], "fraud": False}
    reason = {k: finding[k] for k in ("code", "label", "severity", "message", "audience")}
    row.decision, row.status = "Hold", decide.STATUS["Hold"]
    row.decision_reasons = [reason]
    row.finished_at = utcnow()
    has_decision = db.scalar(select(RunStage.id).where(
        RunStage.run_id == run_id, RunStage.stage_order == DECISION_ORDER))
    if has_decision is None:
        db.add(RunStage(run_id=run_id, stage_order=DECISION_ORDER, stage_name="Decision", status="warn",
                        message="On hold: 1 issue(s) need attention.",
                        details={"decision": "Hold", "status": row.status, "reasons": [reason], "fraud": False,
                                 "alerts": {"AP": [SYSTEM_ERROR]}, "findings": [finding]},
                        duration_ms=0))
    db.commit()


def recover_interrupted_runs(db: Session) -> int:
    """On startup: runs left 'running' by a restart are closed as Hold so their streams can end."""
    ids = db.scalars(select(Invoice.run_id).where(Invoice.status == "running")).all()
    for run_id in ids:
        fail_run(db, run_id, "The server restarted while this invoice was being checked, so a person needs to review it.")
    return len(ids)
