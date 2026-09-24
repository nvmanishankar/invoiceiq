"""The vendor's response link (build guide section 10, 'Vendor response link').

A vendor email for a Hold carries /respond/{token}. The page shows only what the vendor already knows or needs:
our name, theirs, the invoice's number, date, total and PO, and the issues addressed to them. Submitting a PDF starts
a corrected run through the same path as a reviewer's upload (linked, the original superseded), marks the token
used and tells AP. The vendor never sees the decision.
"""

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import alerts
from app.models import Alert, CompanySettings, Invoice, Review, clip, utcnow
from app.services import review
from app.services import runs as run_service
from app.services.vendor_email import vendor_findings
from app.utils.money import format_inr
from app.utils.timefmt import as_utc, iso

log = logging.getLogger(__name__)
VENDOR_ROLE = "Vendor (response link)"
MESSAGE_MAX = 1_000
RECEIVED = "Received, we're checking it"

GONE = {
    "used": "A corrected invoice was already sent with this link, so it can't be used again.",
    "replaced": "This link was replaced by a newer email from us. Please use the link in that email.",
    "expired": "This link has expired. Please reply to our email with the corrected invoice attached.",
    "closed": "This invoice no longer needs a correction from you, so the link has been closed.",
}


class RespondError(Exception):
    def __init__(self, status: int, message: str, state: str):
        super().__init__(message)
        self.status, self.message, self.state = status, message, state


@dataclass
class Link:
    alert: Alert
    run: Invoice


def _gone(state: str) -> RespondError:
    return RespondError(410, GONE[state], state)


def open_link(db: Session, token: str) -> Link:
    """The alert and run behind a token that can still be used; otherwise 404 or 410 with the reason."""
    alert = db.scalar(select(Alert).where(Alert.response_token == token)) if token else None
    run = db.get(Invoice, alert.run_id) if alert is not None else None
    if alert is None or run is None or alert.audience != "Vendor":
        raise RespondError(404, "We couldn't find this link. Please check it was copied in full.", "not_found")
    if alert.token_used_at is not None:
        raise _gone("used")
    if run.status not in review.REVIEWABLE or alerts.run_has_fraud(db, run.run_id):
        raise _gone("closed")
    if alert.token_expires is None or as_utc(alert.token_expires) <= utcnow():
        newer = db.scalar(select(Alert.alert_id).where(Alert.run_id == run.run_id, Alert.alert_id > alert.alert_id,
                                                       Alert.response_token.is_not(None)).limit(1))
        raise _gone("replaced" if newer is not None else "expired")
    return Link(alert, run)


def view(db: Session, token: str) -> dict:
    """Vendor-safe fields only. No other findings, no bank details, no run internals."""
    link = open_link(db, token)
    run = link.run
    company = db.scalar(select(CompanySettings).limit(1))
    stages = review._stages(db, run.run_id)
    issues = list(dict.fromkeys(f["message"] for f in vendor_findings(stages)))
    return {
        "company_name": company.name if company else None,
        "vendor_name": alerts.vendor_names(run.vendor, (run.extraction or {}).get("vendor_name"))[0],
        "invoice_no": run.invoice_no,
        "invoice_date": iso(run.invoice_date),
        "total_display": format_inr(run.total_paise) if run.total_paise is not None else None,
        "po_id": run.po_id,
        "issues": issues,
        "expires_on": f"{link.alert.token_expires:%d %b %Y}",  # as the email printed it
        "message_max": MESSAGE_MAX,
    }


def submit(db: Session, token: str, file_bytes: bytes, file_name: str | None, message: str | None) -> str:
    """Start the corrected run. Returns its run id for the caller to process; the vendor is only told RECEIVED."""
    message = (message or "").strip() or None
    if message and len(message) > MESSAGE_MAX:
        raise RespondError(422, f"The message is longer than {MESSAGE_MAX:,} characters.", "invalid")
    if not file_bytes.startswith(b"%PDF"):
        raise RespondError(415, "That file isn't a PDF. Please upload the corrected invoice as a PDF.", "invalid")
    link = open_link(db, token)
    link.alert.token_used_at = utcnow()
    db.flush()  # before supersede discards drafts: a used link's email is kept
    reason = "Vendor responded via link" + (f". Their message: {message}" if message else ".")
    db.add(Review(run_id=link.run.run_id, reviewer=clip(Review, "reviewer", VENDOR_ROLE), action="vendor_response",
                  reason=reason))
    try:
        new_id = run_service.create_corrected_run(db, link.run, file_bytes, file_name, VENDOR_ROLE)
    except run_service.DailyCapReached:
        db.rollback()
        raise RespondError(429, "We can't take uploads right now. Please try again tomorrow, or reply to our email "
                                "with the PDF attached.", "busy")
    except review.ReviewError:
        db.rollback()
        raise _gone("closed")
    try:
        alerts.vendor_responded(db, link.run, new_id, message)
    except Exception:  # the corrected run is in; a failed AP note mustn't lose it
        log.exception("AP alert for the vendor response on %s failed", link.run.run_id)
        db.rollback()
    return new_id
