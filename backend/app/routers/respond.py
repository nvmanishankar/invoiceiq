"""The vendor's response link: public, no role, vendor-safe data only (build guide section 12)."""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.db import SessionLocal, get_db
from app.services import respond
from app.services import runs as run_service

router = APIRouter(prefix="/api/respond", tags=["respond"])


def _error(e: respond.RespondError) -> JSONResponse:
    """`state` lets the page say why: not_found / used / replaced / expired / closed / invalid / busy."""
    return JSONResponse({"detail": e.message, "state": e.state}, status_code=e.status)


@router.get("/{token}")
def get_response_page(token: str, db: Session = Depends(get_db)):
    try:
        return respond.view(db, token)
    except respond.RespondError as e:
        return _error(e)


def _submit(token: str, data: bytes, name: str, message: str | None) -> str:
    with SessionLocal() as db:
        return respond.submit(db, token, data, name, message)


@router.post("/{token}", status_code=202)
async def post_response(token: str, request: Request, background: BackgroundTasks):
    """Multipart `file` (a PDF, same limit as uploads) and an optional `message`. Never says what was decided."""
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        return _error(respond.RespondError(415, "Please upload the corrected invoice as a PDF.", "invalid"))
    form = await request.form()
    upload, message = form.get("file"), form.get("message")
    if not isinstance(upload, UploadFile):
        return _error(respond.RespondError(400, "Please choose the corrected invoice PDF.", "invalid"))
    data = await upload.read(run_service.MAX_UPLOAD_BYTES + 1)
    if not data:
        return _error(respond.RespondError(400, "The uploaded file is empty.", "invalid"))
    if len(data) > run_service.MAX_UPLOAD_BYTES:
        mb = run_service.MAX_UPLOAD_BYTES // (1024 * 1024)
        return _error(respond.RespondError(413, f"The file is larger than {mb} MB.", "invalid"))
    try:
        new_id = await run_in_threadpool(_submit, token, data, Path(upload.filename or "corrected.pdf").name,
                                         message if isinstance(message, str) else None)
    except respond.RespondError as e:
        return _error(e)
    background.add_task(run_service.execute_run, new_id)
    return {"message": respond.RECEIVED}
