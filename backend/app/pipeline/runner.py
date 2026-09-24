"""Runs the stages in order and writes one run_stages row per stage (build guide section 8)."""

import hashlib
import time
import uuid
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CompanySettings, Invoice, RunStage, utcnow
from app.pipeline import s1_read, s2_extract
from app.pipeline.context import RunContext, StageResult

# Stages 3-9 and the decision are added in phase 5.
STAGES: list[tuple[str, Callable[[RunContext], StageResult]]] = [
    ("Read document", s1_read.run),
    ("Extract fields", s2_extract.run),
]


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def new_run_id() -> str:
    return f"RUN-{uuid.uuid4().hex[:10].upper()}"


def create_run(db: Session, file_bytes: bytes, file_name: str | None = None) -> RunContext:
    company = db.scalar(select(CompanySettings).limit(1))
    ctx = RunContext(
        run_id=new_run_id(),
        file_bytes=file_bytes,
        file_hash=file_hash(file_bytes),
        company=company,
        db=db,
        file_name=file_name,
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


def run_pipeline(
    ctx: RunContext,
    start_at: int = 0,
    min_stage_ms: int | None = None,
    on_stage: Callable[[int, str, StageResult], None] | None = None,
) -> RunContext:
    min_ms = settings.MIN_STAGE_MS if min_stage_ms is None else min_stage_ms
    for order, (name, fn) in enumerate(STAGES[start_at:], start=start_at + 1):
        t0 = time.monotonic()
        try:
            result = fn(ctx)
        except Exception as e:  # never crash the run
            ctx.db.rollback()
            ctx.add("sys", "hold", f"The '{name}' step hit an unexpected error, so a person needs to review this invoice.",
                    ["AP"], {"error": f"{type(e).__name__}: {e}"})
            result = StageResult("fail", f"{name} failed; sent to review", {"error": f"{type(e).__name__}: {e}"})
        pad_to_min_duration(t0, min_ms)
        save_stage(ctx, order, name, result, t0)
        if on_stage:
            on_stage(order, name, result)
        if ctx.halt:
            break
    row = ctx.db.get(Invoice, ctx.run_id)
    if row is not None:
        row.finished_at = utcnow()
        ctx.db.commit()
    return ctx
