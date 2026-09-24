"""Company settings: details (read-only), tolerance and vendor auto-send."""

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.db import get_db
from app.roles import require_finance
from app.services import company

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    return company.settings_dict(company.get_company(db))


@router.patch("")
def update_settings(body: company.SettingsIn, x_role: str | None = Header(None), db: Session = Depends(get_db)):
    """Applies from the next run: each run reads the settings when it starts. Tolerance is Finance-only."""
    if body.tolerance_pct is not None or body.tolerance_cap is not None:
        require_finance(x_role, "change the tolerance")
    return company.settings_dict(company.update_settings(db, body))
