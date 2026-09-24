"""Runs: start, live stream, list, detail, original PDF; plus the sample list (build guide section 12)."""

import asyncio
import json
import re
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.db import SessionLocal, get_db
from app.models import Invoice, RunFile, RunStage, Vendor
from app.services import runs as run_service
from app.services.views import decision_dict, run_detail, run_summary, stage_dict

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
