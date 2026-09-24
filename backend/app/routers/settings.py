"""Company settings: details (read-only), tolerance and vendor auto-send."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import company

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    return company.settings_dict(company.get_company(db))


@router.patch("")
def update_settings(body: company.SettingsIn, db: Session = Depends(get_db)):
    """Applies from the next run: each run reads the settings when it starts."""
    return company.settings_dict(company.update_settings(db, body))
