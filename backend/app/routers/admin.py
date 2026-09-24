"""Admin: reset the demo data and run the test suite (build guide sections 12 and 17)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import seed
from app.services import test_suite

router = APIRouter(prefix="/api/admin", tags=["admin"])


class ResetBody(BaseModel):
    confirm: str = ""


@router.post("/reset")
def reset(body: ResetBody):
    if body.confirm != "RESET":
        raise HTTPException(400, 'To wipe every run and restore the demo data, send {"confirm": "RESET"}.')
    seed.reset()
    return {"ok": True, "message": "All runs deleted and the demo data restored."}


@router.post("/test-suite")
def run_test_suite():
    """Every sample on a scratch database; the live data is never touched. Sync, so it runs in the threadpool."""
    try:
        return test_suite.run_suite()
    except test_suite.SuiteBusy as e:
        raise HTTPException(409, str(e))
    except test_suite.SuiteCoolingDown as e:
        raise HTTPException(429, str(e), headers={"Retry-After": str(e.wait)})
