"""Company settings: details are read-only; tolerance and vendor auto-send can be changed.

Every run reads these when it starts, so a change applies from the next invoice on.
"""

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CompanySettings
from app.services.errors import Invalid
from app.utils.gstin import state_label
from app.utils.money import format_inr, rupees_to_paise

MAX_TOLERANCE_PCT = 10.0
MAX_TOLERANCE_CAP_RUPEES = 100_000


class SettingsIn(BaseModel):
    tolerance_pct: float | None = None  # percent, e.g. 2 for 2%
    tolerance_cap: float | None = None  # rupees
    vendor_auto_send: bool | None = None


def get_company(db: Session) -> CompanySettings:
    return db.scalar(select(CompanySettings).limit(1))


def settings_dict(c: CompanySettings) -> dict:
    return {
        "company": {
            "name": c.name,
            "address": c.address,
            "country": c.country,
            "gstin": c.gstin,
            "state_code": c.state_code,
            "state": state_label(c.state_code) if c.state_code else None,
            "currency": c.currency,
            "ap_email": c.ap_email,
            "procurement_email": c.procurement_email,
            "finance_email": c.finance_email,
        },
        "tolerance_pct": round(c.tolerance_pct * 100, 4),
        "tolerance_cap_paise": c.tolerance_abs_paise,
        "tolerance_cap_display": format_inr(c.tolerance_abs_paise),
        "vendor_auto_send": c.vendor_auto_send,
        # Deployment switches from the environment; when off they win over the toggle above.
        "emails_enabled": settings.SEND_EMAILS,
        "vendor_auto_send_allowed": settings.VENDOR_AUTO_SEND,
    }


def update_settings(db: Session, body: SettingsIn) -> CompanySettings:
    c = get_company(db)
    errors: dict[str, str] = {}
    if body.tolerance_pct is not None and not 0 <= body.tolerance_pct <= MAX_TOLERANCE_PCT:
        errors["tolerance_pct"] = f"Tolerance is a percentage from 0 to {MAX_TOLERANCE_PCT:g}."
    if body.tolerance_cap is not None and not 0 <= body.tolerance_cap <= MAX_TOLERANCE_CAP_RUPEES:
        errors["tolerance_cap"] = f"The cap is an amount from ₹0 to {format_inr(MAX_TOLERANCE_CAP_RUPEES * 100)}."
    if errors:
        raise Invalid(errors)
    if body.tolerance_pct is not None:
        c.tolerance_pct = round(body.tolerance_pct / 100, 6)
    if body.tolerance_cap is not None:
        c.tolerance_abs_paise = rupees_to_paise(body.tolerance_cap)
    if body.vendor_auto_send is not None:
        c.vendor_auto_send = body.vendor_auto_send
    db.commit()
    return c
