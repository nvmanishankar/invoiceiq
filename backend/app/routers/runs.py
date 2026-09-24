"""Runs: start, live stream, list, detail, original PDF; plus the sample list (build guide section 12)."""

import asyncio
import json
import re
from pathlib import Path

from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.db import SessionLocal, get_db
from app.models import Invoice, RunFile, RunStage, Vendor
from app.services import review as review_service
from app.services import runs as run_service
from app.services.views import decision_dict, run_detail, run_summary, stage_dict, waiting_since

router = APIRouter(prefix="/api", tags=["runs"])

POLL_SECONDS = 0.4
KEEPALIVE_SECONDS = 15


async def _read_request(request: Request) -> tuple[bytes, str]:
    """multipart `file`, or `sample_name` as a form field or JSON."""
    ctype = request.headers.get("content-type", "")
    if ctype.startswith(("multipart/form-data", "application/x-www-form-urlencoded")):
        form = await request.form()
        upload, sample = form.get("file"), form.get("sample_name")
    elif ctype.startswith("application/json"):
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "The request body isn't valid JSON.")
        upload, sample = None, body.get("sample_name") if isinstance(body, dict) else None
    else:
        raise HTTPException(415, "Send a PDF as multipart field 'file', or a 'sample_name'.")

    if isinstance(upload, UploadFile):
        data = await upload.read(run_service.MAX_UPLOAD_BYTES + 1)
        if not data:
            raise HTTPException(400, "The uploaded file is empty.")
        if len(data) > run_service.MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"The file is larger than {run_service.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
        return data, Path(upload.filename or "upload.pdf").name
    if isinstance(sample, str) and sample:
        if sample not in run_service.sample_names():  # also blocks paths like ../../etc
            raise HTTPException(404, f"There's no sample called '{sample}'. See GET /api/samples.")
        return (run_service.SAMPLES_DIR / sample).read_bytes(), sample
    raise HTTPException(400, "Send a PDF as multipart field 'file', or a 'sample_name'.")


@router.post("/runs", status_code=202)
async def create_run(request: Request, background: BackgroundTasks):
    data, name = await _read_request(request)
    try:
        run_id = await run_in_threadpool(run_service.start_run, data, name)
    except run_service.DailyCapReached as e:
        raise HTTPException(429, str(e))
    background.add_task(run_service.execute_run, run_id)
    return {"run_id": run_id}


def _poll(run_id: str, after: int) -> tuple[list[dict], dict | None]:
    """New stage rows after `after`, plus the decision once the run has finished."""
    with SessionLocal() as db:
        # Read the run first: if it's finished then, every stage row is already committed.
        run = db.get(Invoice, run_id)
        finished = run is not None and run.status != "running" and run.finished_at is not None
        rows = db.scalars(select(RunStage).where(RunStage.run_id == run_id, RunStage.stage_order > after)
                          .order_by(RunStage.stage_order)).all()
        return [stage_dict(r) for r in rows], decision_dict(db, run) if finished else None


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/runs/{run_id}/stream")
async def stream(run_id: str, db: Session = Depends(get_db)):
    """SSE: replays stages already written, then follows new ones. Refresh-safe and multi-viewer."""
    if db.get(Invoice, run_id) is None:
        raise HTTPException(404, f"Run {run_id} not found.")

    async def events():
        sent, idle = 0, 0.0
        yield ": connected\n\n"
        while True:
            stages, decision = await run_in_threadpool(_poll, run_id, sent)
            for s in stages:
                yield _sse("stage", s)
                sent = s["order"]
            if decision is not None:
                yield _sse("decision", decision)
                yield _sse("done", {})
                return
            idle = 0.0 if stages else idle + POLL_SECONDS
            if idle >= KEEPALIVE_SECONDS:
                yield ": keepalive\n\n"
                idle = 0.0
            await asyncio.sleep(POLL_SECONDS)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/runs")
def list_runs(
    status: str | None = None,
    vendor: str | None = Query(None, description="vendor id or part of the name"),
    q: str | None = Query(None, description="search run id, invoice no, file, PO, vendor"),
    include_seed: bool = False,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(Invoice).outerjoin(Vendor, Vendor.vendor_id == Invoice.vendor_id)
    if not include_seed:
        stmt = stmt.where(Invoice.is_seed.is_(False))
    if status:
        stmt = stmt.where(Invoice.status == status)
    if vendor:
        stmt = stmt.where(or_(Invoice.vendor_id == vendor, Vendor.name.ilike(f"%{vendor}%")))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Invoice.run_id.ilike(like), Invoice.invoice_no.ilike(like), Invoice.file_name.ilike(like),
                              Invoice.po_id.ilike(like), Vendor.name.ilike(like)))
    rows = db.scalars(stmt.order_by(Invoice.created_at.desc()).limit(limit)).all()
    return [run_summary(r) for r in rows]


def _get_run(db: Session, run_id: str) -> Invoice:
    inv = db.get(Invoice, run_id)
    if inv is None:
        raise HTTPException(404, f"Run {run_id} not found.")
    return inv


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    return run_detail(db, _get_run(db, run_id))


@router.get("/runs/{run_id}/file")
def get_file(run_id: str, db: Session = Depends(get_db)):
    _get_run(db, run_id)
    stored = db.get(RunFile, run_id)
    if stored is None:
        raise HTTPException(404, "There's no stored file for this run (seed ledger entries have none).")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", stored.file_name or f"{run_id}.pdf")
    return Response(stored.data, media_type=stored.content_type,
                    headers={"Content-Disposition": f'inline; filename="{safe}"'})


@router.get("/samples")
def list_samples():
    return run_service.samples()


class ReviewBody(BaseModel):
    action: Literal["confirm", "pick_po", "override", "send_to_vendor", "reject", "send_reminder"]
    fields: dict[str, Any] = Field(default_factory=dict, description="confirm: corrections, as the extraction stores them")
    po_id: str | None = None
    reason: str | None = None
    note: str | None = None
    reasons: list[str] | None = Field(None, description="send_to_vendor: ticked case codes, plus 'other'")
    subject: str | None = Field(None, description="send_to_vendor: the email subject as the reviewer left it")
    body: str | None = Field(None, description="send_to_vendor: the email body as the reviewer left it")


@router.post("/runs/{run_id}/review")
def review_run(run_id: str, payload: ReviewBody, background: BackgroundTasks,
               x_role: str | None = Header(None, description="Procurement / AP clerk / Finance"),
               db: Session = Depends(get_db)):
    """Confirm (resume from stage 3), pick PO (resume from stage 6), override, send to vendor, remind the vendor,
    or reject."""
    try:
        out = review_service.apply(db, run_id, payload.action, x_role, fields=payload.fields, po_id=payload.po_id,
                                   reason=payload.reason, note=payload.note, reasons=payload.reasons,
                                   subject=payload.subject, body=payload.body)
    except review_service.ReviewError as e:
        db.rollback()
        raise HTTPException(e.status, e.message)
    if out.resume_from is not None:
        background.add_task(run_service.resume_run, run_id, out.resume_from)
    return {"run_id": out.run_id, "action": out.action, "status": out.status, "resumed": out.resume_from is not None}


class PreviewBody(BaseModel):
    reasons: list[str] | None = None
    note: str | None = None


def _preview(db: Session, run_id: str, reasons: list[str] | None, note: str | None) -> dict:
    try:
        return review_service.email_preview(db, run_id, reasons, note)
    except review_service.ReviewError as e:
        raise HTTPException(e.status, e.message)


@router.get("/runs/{run_id}/vendor-email-preview")
def vendor_email_preview(run_id: str, db: Session = Depends(get_db)):
    """The reason chips, the drafted note and the email with every reason ticked. Nothing is sent."""
    return _preview(db, run_id, None, None)


@router.post("/runs/{run_id}/vendor-email-preview")
def vendor_email_preview_for(run_id: str, payload: PreviewBody, db: Session = Depends(get_db)):
    """The email for the reasons and note the reviewer chose. Nothing is sent."""
    return _preview(db, run_id, payload.reasons, payload.note)


@router.post("/runs/{run_id}/corrected", status_code=202)
async def upload_corrected(run_id: str, request: Request, background: BackgroundTasks,
                           x_role: str | None = Header(None, description="Procurement / AP clerk / Finance")):
    """A corrected invoice for a held run: a new run (parent_upload_id = this run), checked from stage 1.
    This run becomes 'superseded' and leaves the review queue."""
    data, name = await _read_request(request)
    try:
        new_id = await run_in_threadpool(run_service.start_corrected_run, run_id, data, name, x_role)
    except review_service.ReviewError as e:
        raise HTTPException(e.status, e.message)
    except run_service.DailyCapReached as e:
        raise HTTPException(429, str(e))
    background.add_task(run_service.execute_run, new_id)
    return {"run_id": new_id, "replaces": run_id}


@router.get("/review-queue")
def review_queue(db: Session = Depends(get_db)):
    """Runs waiting for a person, oldest first (they've waited longest). `waiting` lists the runs parked on the
    vendor, longest wait first; they aren't in `count`."""
    rows = db.scalars(select(Invoice).where(Invoice.status == "needs_review").order_by(Invoice.created_at)).all()
    parked = [{**run_summary(r), "waiting_since": waiting_since(db, r)}
              for r in db.scalars(select(Invoice).where(Invoice.status == "waiting_on_vendor"))]
    parked.sort(key=lambda r: r["waiting_since"] or r["created_at"] or "")
    return {"count": len(rows), "runs": [run_summary(r) for r in rows], "waiting": parked}
