"""Runs the stages in order and writes one run_stages row per stage (build guide section 8)."""

import hashlib
import time
import uuid
from collections.abc import Callable
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CompanySettings, Invoice, RunStage, utcnow
from app.pipeline import (
    decide,
    s1_read,
    s2_extract,
    s3_validate,
    s4_vendor,
    s5_po_match,
    s6_amounts,
    s7_duplicates,
    s8_tax,
    s9_dates,
)
from app.pipeline.context import SYSTEM_ERROR, RunContext, StageResult

STAGES: list[tuple[str, Callable[[RunContext], StageResult]]] = [
    ("Read document", s1_read.run),
    ("Extract fields", s2_extract.run),
    ("Completeness and maths", s3_validate.run),
    ("Verify vendor", s4_vendor.run),
    ("Match PO", s5_po_match.run),
    ("Amounts and quantities", s6_amounts.run),
    ("Duplicates", s7_duplicates.run),
    ("Tax", s8_tax.run),
    ("Dates and terms", s9_dates.run),
]
HALTING_STAGES = 2  # only stages 1-2 may stop the run: later stages have nothing to check
DECISION = ("Decision", decide.run)


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def new_run_id() -> str:
    return f"RUN-{uuid.uuid4().hex[:10].upper()}"


def create_run(db: Session, file_bytes: bytes, file_name: str | None = None, today: date | None = None) -> RunContext:
    company = db.scalar(select(CompanySettings).limit(1))
    ctx = RunContext(
        run_id=new_run_id(),
        file_bytes=file_bytes,
        file_hash=file_hash(file_bytes),
        company=company,
        db=db,
        file_name=file_name,
        today=today or date.today(),
    )
    db.add(Invoice(run_id=ctx.run_id, file_name=file_name, file_hash=ctx.file_hash, status="running"))
    db.commit()
    return ctx


def pad_to_min_duration(t0: float, min_ms: int) -> None:
    left = min_ms / 1000 - (time.monotonic() - t0)
    if left > 0:
        time.sleep(left)


def save_stage(ctx: RunContext, order: int, name: str, result: StageResult, t0: float) -> None:
    ctx.db.add(RunStage(
        run_id=ctx.run_id,
        stage_order=order,
        stage_name=name,
        status=result.status,
        message=result.message,
        details=result.details,
        duration_ms=int((time.monotonic() - t0) * 1000),
    ))
    ctx.db.commit()


def _run_stage(ctx: RunContext, name: str, fn: Callable[[RunContext], StageResult]) -> StageResult:
    try:
        return fn(ctx)
    except Exception as e:  # never crash the run
        ctx.db.rollback()
        error = f"{type(e).__name__}: {e}"
        ctx.add(SYSTEM_ERROR, "hold", f"System error: the '{name}' step failed, so a person needs to review this invoice.",
                ["AP"], {"stage": name, "error": error})
        return StageResult("fail", f"System error in {name}; sent to review", {"error": error})


def run_pipeline(
    ctx: RunContext,
    start_at: int = 0,
    min_stage_ms: int | None = None,
    on_stage: Callable[[int, str, StageResult], None] | None = None,
) -> RunContext:
    """Run every check, then decide. Only stages 1-2 may halt; the decision always runs."""
    min_ms = settings.MIN_STAGE_MS if min_stage_ms is None else min_stage_ms
    for order, (name, fn) in enumerate(STAGES[start_at:], start=start_at + 1):
        t0 = time.monotonic()
        result = _run_stage(ctx, name, fn)
        pad_to_min_duration(t0, min_ms)
        save_stage(ctx, order, name, result, t0)
        if on_stage:
            on_stage(order, name, result)
        if ctx.halt and order <= HALTING_STAGES:
            break
        ctx.halt = False  # a later stage can't stop the run

    t0 = time.monotonic()
    name, fn = DECISION
    result = _run_stage(ctx, name, fn)
    if ctx.decision is None:  # the decision step itself failed: the sys finding makes it a Hold
        ctx.decision = decide.decide(ctx.findings)
        row = ctx.db.get(Invoice, ctx.run_id)
        if row is not None:
            row.decision, row.status = ctx.decision, decide.STATUS[ctx.decision]
    pad_to_min_duration(t0, min_ms)
    save_stage(ctx, len(STAGES) + 1, name, result, t0)
    if on_stage:
        on_stage(len(STAGES) + 1, name, result)

    row = ctx.db.get(Invoice, ctx.run_id)
    if row is not None:
        row.finished_at = utcnow()
        ctx.db.commit()
    return ctx
