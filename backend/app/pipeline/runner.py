"""Runs the stages in order and writes one run_stages row per stage (build guide section 8)."""

import hashlib
import json
import logging
import time
import uuid
from collections.abc import Callable
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CompanySettings, Invoice, RunFile, RunStage, clip, utcnow
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
    split,
)
from app.pipeline.context import SYSTEM_ERROR, Finding, RunContext, StageResult
from app.schemas import ExtractedInvoice
from app.services.matching import needed_pairs, pair_lines, similarity_table
from app.utils.money import format_inr

log = logging.getLogger(__name__)

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
DECISION_ORDER = len(STAGES) + 1
SPLIT_RESUME_AT = HALTING_STAGES  # a split child has stages 1-2 written for it; 3 onwards runs as for a review


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def new_run_id() -> str:
    return f"RUN-{uuid.uuid4().hex[:10].upper()}"


def create_run(db: Session, file_bytes: bytes, file_name: str | None = None, today: date | None = None,
               store_file: bool = False, run_id: str | None = None, parent_upload_id: str | None = None) -> RunContext:
    """The invoices row (and the file). Anything else pending on `db` is committed with it."""
    company = db.scalar(select(CompanySettings).limit(1))
    ctx = RunContext(
        run_id=run_id or new_run_id(),
        file_bytes=file_bytes,
        file_hash=file_hash(file_bytes),
        company=company,
        db=db,
        file_name=file_name,
        today=today or date.today(),
    )
    db.add(Invoice(run_id=ctx.run_id, parent_upload_id=parent_upload_id, file_name=clip(Invoice, "file_name", file_name),
                   file_hash=ctx.file_hash, status="running"))
    if store_file:
        db.add(RunFile(run_id=ctx.run_id, file_name=clip(RunFile, "file_name", file_name), size=len(file_bytes),
                       data=file_bytes))
    db.commit()
    return ctx


def load_run(db: Session, run_id: str, today: date | None = None) -> RunContext:
    """A context for a run created earlier (e.g. by the API), bound to this session."""
    row = db.get(Invoice, run_id)
    stored = db.get(RunFile, run_id)
    if row is None or stored is None:
        raise LookupError(f"run {run_id} or its file not found")
    return RunContext(
        run_id=run_id,
        file_bytes=stored.data,
        file_hash=row.file_hash or file_hash(stored.data),
        company=db.scalar(select(CompanySettings).limit(1)),
        db=db,
        file_name=row.file_name,
        today=today or date.today(),
    )


def stored_finding(d: dict) -> Finding:
    return Finding(d["code"], d["severity"], d["message"], list(d.get("audience") or []), dict(d.get("evidence") or {}),
                   bool(d.get("fraud")))


def resume_context(db: Session, run_id: str, start_at: int, today: date | None = None) -> RunContext:
    """Rebuild what stages 1..start_at left on the context, from the database, to run the rest again.

    Findings come back from the kept stage rows; vendor and PO from the invoice row (a reviewer may have set them).
    """
    ctx = load_run(db, run_id, today)
    row = db.get(Invoice, run_id)
    kept = db.scalars(select(RunStage).where(RunStage.run_id == run_id, RunStage.stage_order <= start_at)
                      .order_by(RunStage.stage_order)).all()
    by_order = {s.stage_order: s.details or {} for s in kept}
    ctx.findings = [stored_finding(f) for s in kept for f in (s.details or {}).get("findings", [])]
    ctx.page_count = by_order.get(1, {}).get("pages", 0)
    ctx.is_scan = bool(by_order.get(1, {}).get("scanned"))
    if by_order.get(1, {}).get("split_from"):
        ctx.offline = True  # a split child makes no LLM calls: cached answers, else text matching
        ctx.sibling_fraud = split.sibling_fraud(db, run_id)
    ctx.doc_type = row.doc_type
    ctx.extraction = row.extraction
    # LLM budget: what this run already used, so a resume can't take it past the per-run cap.
    ctx.llm_calls = by_order.get(2, {}).get("llm_calls") or 0
    if by_order.get(5, {}).get("similarity_source") == "llm":
        ctx.llm_calls += 1
    if start_at >= 3:
        ctx.bundled = s3_validate.is_bundled(ctx.inv)
    if start_at >= 4:
        ctx.vendor = row.vendor
    if start_at >= 5 and row.po is not None:
        ctx.po, ctx.match_type, ctx.match_confidence = row.po, row.po_match_type, row.match_confidence
        sims = similarity_table(ctx, needed_pairs(ctx.inv.lines, [row.po], skip_exact=True))
        ctx.line_pairs, ctx.unpaired_lines = pair_lines(ctx.inv.lines, row.po, sims)
    return ctx


def pad_to_min_duration(t0: float, min_ms: int) -> None:
    left = min_ms / 1000 - (time.monotonic() - t0)
    if left > 0:
        time.sleep(left)


def finding_dict(f: Finding) -> dict:
    d = {"code": f.code, "label": f.label, "severity": f.severity, "message": f.message,
         "audience": f.audience, "fraud": f.fraud}
    if "Vendor" in f.audience and f.evidence:
        # Kept so a reviewer's email to the vendor can be drafted from the numbers (services/vendor_email.py).
        d["evidence"] = json.loads(json.dumps(f.evidence, default=str))
    return d


def stage_row(run_id: str, order: int, name: str, result: StageResult, t0: float,
              findings: list[Finding] = ()) -> RunStage:
    """One run_stages row; the findings this stage raised go in details["findings"]."""
    return RunStage(
        run_id=run_id,
        stage_order=order,
        stage_name=clip(RunStage, "stage_name", name),
        status=result.status,
        message=result.message,
        details={**result.details, "findings": [finding_dict(f) for f in findings]},
        duration_ms=int((time.monotonic() - t0) * 1000),
    )


def save_stage(ctx: RunContext, order: int, name: str, result: StageResult, t0: float,
               findings: list[Finding] = ()) -> None:
    ctx.db.add(stage_row(ctx.run_id, order, name, result, t0, findings))
    ctx.db.commit()


# --- Case 1.6: several invoices in one file ---------------------------------------------------------------------

def _child_name(file_name: str | None, pages: list[int]) -> str:
    stem = (file_name or "upload.pdf").rsplit(".", 1)[0]
    return f"{stem}_p{pages[0]}.pdf" if len(pages) == 1 else f"{stem}_p{pages[0]}-{pages[-1]}.pdf"


def _add_child(ctx: RunContext, inv: ExtractedInvoice, pages: list[int], part: int, parts: int) -> str:
    """One child run for one invoice of a split file: its own PDF of just its pages, its invoice row filled from
    that invoice's extraction, and stages 1-2 written as done. Added to the session, not committed."""
    t0 = time.monotonic()
    data = split.cut_pages(ctx.file_bytes, pages, ctx.file_hash)
    child = RunContext(run_id=new_run_id(), file_bytes=data, file_hash=file_hash(data), company=ctx.company,
                       db=ctx.db, file_name=_child_name(ctx.file_name, pages), today=ctx.today, doc_type="invoice")
    row = Invoice(run_id=child.run_id, parent_upload_id=ctx.run_id, file_name=clip(Invoice, "file_name", child.file_name),
                  file_hash=child.file_hash, status="running")
    ctx.db.add(row)
    ctx.db.add(RunFile(run_id=child.run_id, file_name=clip(RunFile, "file_name", child.file_name), size=len(data),
                       data=data))
    origin = f"Split from {ctx.run_id}, {split.pages_label(pages)} of {ctx.page_count}"

    if ctx.is_scan:
        child.add("1.2", "info", "This is a scanned image, so it was read visually.", [])
    read = StageResult("pass", origin, {"pages": len(pages), "scanned": ctx.is_scan, "split_from": ctx.run_id,
                                        "source_pages": pages, "source_page_count": ctx.page_count,
                                        "part": part, "parts": parts})
    ctx.db.add(stage_row(child.run_id, 1, STAGES[0][0], read, t0, child.findings))

    seen = len(child.findings)
    low = s2_extract.prepare_invoice(child, inv)
    child.extraction = inv.model_dump(mode="json")
    s2_extract.write_invoice_row(row, "invoice", child.extraction, inv)
    msg = f"{origin}: {len(inv.lines)} line(s), total {format_inr(row.total_paise)}"
    if low:
        msg += f"; low confidence: {', '.join(low)}"
    fields = StageResult("warn" if low else "pass", msg, {"fields": child.extraction, "llm_calls": 0,
                                                            "split_from": ctx.run_id})
    ctx.db.add(stage_row(child.run_id, 2, STAGES[1][0], fields, t0, child.findings[seen:]))
    return child.run_id


def _finish_split(ctx: RunContext, min_ms: int, on_stage) -> RunContext:
    """The parent of a split file: create the children in one commit, then close the parent as 'split' with a
    Decision stage naming them. The parent has no decision; each child gets its own when run_children checks it."""
    t0 = time.monotonic()
    parts = ctx.split_parts
    try:
        ids = [_add_child(ctx, inv, pages, i, len(parts)) for i, (inv, pages) in enumerate(parts, start=1)]
        row = ctx.db.get(Invoice, ctx.run_id)
        row.doc_type = "invoice"
        ctx.db.commit()
    except Exception as e:  # never crash the run: without its children the file is held for a person
        ctx.db.rollback()
        log.exception("splitting run %s failed", ctx.run_id)
        ctx.split_parts = None
        ctx.add(SYSTEM_ERROR, "hold", "System error: this file holds several invoices and splitting it failed, so "
                                      "a person needs to review it.", ["AP"], {"error": f"{type(e).__name__}: {e}"})
        return None
    ctx.children = ids
    result = StageResult("info", f"Split into {len(ids)} invoices: {', '.join(ids)}", {
        "decision": None,
        "status": split.SPLIT,
        "children": [{"run_id": rid, "pages": pages} for rid, (_, pages) in zip(ids, parts)],
        "llm_calls": ctx.llm_calls,
    })
    pad_to_min_duration(t0, min_ms)
    save_stage(ctx, DECISION_ORDER, DECISION[0], result, t0)
    if on_stage:
        on_stage(DECISION_ORDER, DECISION[0], result)
    row.status, row.decision, row.finished_at = split.SPLIT, None, utcnow()  # together: the stream ends on this
    ctx.db.commit()
    return ctx


def run_children(db: Session, run_ids: list[str], today: date | None = None, min_stage_ms: int | None = None,
                 on_stage: Callable[[int, str, StageResult], None] | None = None) -> list[RunContext]:
    """Check a split file's children from stage 3, one after another in page order (never in parallel), so each
    sees the PO balances its earlier siblings left."""
    return [run_pipeline(resume_context(db, rid, SPLIT_RESUME_AT, today), start_at=SPLIT_RESUME_AT,
                         min_stage_ms=min_stage_ms, on_stage=on_stage) for rid in run_ids]


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
        seen = len(ctx.findings)
        result = _run_stage(ctx, name, fn)
        pad_to_min_duration(t0, min_ms)
        save_stage(ctx, order, name, result, t0, ctx.findings[seen:])
        if on_stage:
            on_stage(order, name, result)
        if ctx.halt and order <= HALTING_STAGES:
            break
        ctx.halt = False  # a later stage can't stop the run

    t0 = time.monotonic()
    seen = len(ctx.findings)
    if ctx.split_parts and _finish_split(ctx, min_ms, on_stage) is not None:
        return ctx
    name, fn = DECISION
    result = _run_stage(ctx, name, fn)
    if ctx.decision is None:  # the decision step itself failed: the sys finding makes it a Hold
        ctx.decision = decide.decide(ctx.findings)
        row = ctx.db.get(Invoice, ctx.run_id)
        if row is not None:
            row.decision, row.status = ctx.decision, decide.STATUS[ctx.decision]
    pad_to_min_duration(t0, min_ms)
    save_stage(ctx, DECISION_ORDER, name, result, t0, ctx.findings[seen:])
    if on_stage:
        on_stage(DECISION_ORDER, name, result)

    row = ctx.db.get(Invoice, ctx.run_id)
    if row is not None:
        row.finished_at = utcnow()
        ctx.db.commit()
    return ctx
