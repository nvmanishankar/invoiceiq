"""Dashboard numbers (build guide section 13)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import stats as stats_service

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def stats(
    tz_offset: int = Query(0, ge=-14 * 60, le=14 * 60, description="viewer's minutes ahead of UTC (IST = 330)"),
    days: int = Query(14, ge=1, le=90, description="days in the decisions-per-day series"),
    db: Session = Depends(get_db),
):
    return stats_service.compute(db, tz_offset_minutes=tz_offset, days=days)
