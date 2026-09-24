"""Admin: reset the demo data (build guide section 12)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import seed

router = APIRouter(prefix="/api/admin", tags=["admin"])


class ResetBody(BaseModel):
    confirm: str = ""


@router.post("/reset")
def reset(body: ResetBody):
    if body.confirm != "RESET":
        raise HTTPException(400, 'To wipe every run and restore the demo data, send {"confirm": "RESET"}.')
    seed.reset()
    return {"ok": True, "message": "All runs deleted and the demo data restored."}
