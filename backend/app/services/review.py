"""Human review of a held run (build guide section 11).

Every action is logged in `reviews` with before/after values. Confirm and pick_po rewind the run
and hand back the stage to resume from; the caller runs the rest in the background, and the
existing SSE stream shows it live. Override, send_to_vendor and reject close or park the run here; a corrected upload supersedes it.
send_reminder re-sends the last vendor email with a fresh response link.
"""

from dataclasses import dataclass
from datetime import date

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import alerts
from app.models import Invoice, PurchaseOrder, Review, RunStage, clip, utcnow
from app.pipeline.context import code_label
from app.pipeline.runner import DECISION_ORDER, HALTING_STAGES
from app.pipeline.s2_extract import write_invoice_row
from app.roles import DEFAULT_ROLE
from app.roles import FINANCE as FINANCE_ROLE
from app.schemas import ExtractedInvoice
from app.services import vendor_email
from app.utils.money import format_inr

ACTIONS = ("confirm", "pick_po", "override", "send_to_vendor", "reject", "send_reminder")
REVIEWABLE = ("needs_review", "waiting_on_vendor")
SUPERSEDED = "superseded"  # a corrected invoice replaced this run; its decision stays as it was
RESUME_AFTER_CONFIRM = HALTING_STAGES  # stages 1-2 are kept; 3 onwards runs again
RESUME_AFTER_PICK_PO = 5  # stages 1-5 are kept; 6 onwards runs again
PICKED_MATCH_TYPE = "Explicit (reviewer)"

# Fields a reviewer may correct, as the extraction stores them (money in rupees, dates ISO).
TEXT_FIELDS = ("vendor_name", "vendor_gstin", "invoice_number", "po_reference", "currency", "bank_account", "ifsc")
MONEY_FIELDS = ("subtotal", "cgst", "sgst", "igst", "total")
DATE_FIELDS = ("invoice_date",)
INT_FIELDS = ("payment_terms_days",)
EDITABLE_FIELDS = TEXT_FIELDS + MONEY_FIELDS + DATE_FIELDS + INT_FIELDS
FIELD_LABELS = {
    "vendor_name": "Vendor name", "vendor_gstin": "Vendor GSTIN", "invoice_number": "Invoice number",
    "po_reference": "PO reference", "currency": "Currency", "bank_account": "Bank account", "ifsc": "IFSC",
    "subtotal": "Subtotal", "cgst": "CGST", "sgst": "SGST", "igst": "IGST", "total": "Total",
    "invoice_date": "Invoice date", "payment_terms_days": "Payment terms (days)",
}


class ReviewError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class Outcome:
    run_id: str
    action: str
    status: str
    resume_from: int | None = None  # stage index to resume at (0-based, as run_pipeline's start_at)


# --- Helpers --------------------------------------------------------------------------------------------------------

def _stages(db: Session, run_id: str) -> list[RunStage]:
    return list(db.scalars(select(RunStage).where(RunStage.run_id == run_id).order_by(RunStage.stage_order)))


def _findings(stages: list[RunStage]) -> list[dict]:
    return [f for s in stages for f in (s.details or {}).get("findings", [])]


def _has_fraud(stages: list[RunStage]) -> bool:
    return any(f.get("fraud") for f in _findings(stages))


def _required(text: str | None, what: str) -> str:
    text = (text or "").strip()
    if not text:
        raise ReviewError(422, f"Please give a {what}.")
    return text


def _log(db: Session, run_id: str, role: str, action: str, reason: str | None, changes: dict | None) -> Review:
    entry = Review(run_id=run_id, reviewer=clip(Review, "reviewer", role), action=action, reason=reason,
                   field_changes=changes or None)
    db.add(entry)
    return entry


def _rewind(db: Session, row: Invoice, keep_through: int) -> None:
    """Delete stage rows after `keep_through` and clear what those stages decided, so they can run again."""
    db.execute(delete(RunStage).where(RunStage.run_id == row.run_id, RunStage.stage_order > keep_through))
    row.status, row.decision, row.decision_reasons = "running", None, None
    row.due_date, row.finished_at = None, None
    if keep_through < 4:
        row.vendor_id = None
    if keep_through < 5:
        row.po_id, row.po_match_type, row.match_confidence = None, "None", None
    for line in row.lines:
        line.matched_po_line = None


def _money_text(field: str, value) -> str:
    return format_inr(round(value * 100)) if field in MONEY_FIELDS and isinstance(value, int | float) else str(value)


def _clean(field: str, value):
    """A reviewer's value as the extraction stores it. Blank means 'not on the invoice' (null), never a guess."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        if field in MONEY_FIELDS:
            v = float(str(value).replace(",", "").replace("₹", "").strip())
            if v < 0:
                raise ValueError
            return round(v, 2)
        if field in INT_FIELDS:
            v = int(str(value).strip())
            if v < 0:
                raise ValueError
            return v
        if field in DATE_FIELDS:
            return date.fromisoformat(str(value).strip()).isoformat()
    except ValueError:
        kind = "an amount in rupees" if field in MONEY_FIELDS else "a whole number of days" if field in INT_FIELDS \
            else "a date as YYYY-MM-DD"
        raise ReviewError(422, f"{FIELD_LABELS[field]} should be {kind}.")
    return str(value).strip()


def _decision_stage(stages: list[RunStage]) -> RunStage | None:
    return next((s for s in stages if s.stage_order == DECISION_ORDER), None)


def _restamp_decision(stage: RunStage | None, decision: str, status: str, stage_status: str, message: str) -> None:
    if stage is None:
        return
    stage.status, stage.message = stage_status, message
    stage.details = {**(stage.details or {}), "decision": decision, "status": status}


# --- Actions --------------------------------------------------------------------------------------------------------

def confirm(db: Session, row: Invoice, stages: list[RunStage], role: str, fields: dict) -> Outcome:
    if row.doc_type not in (None, "invoice"):
        raise ReviewError(409, f"This document is a {row.doc_type.replace('_', ' ')}, not an invoice, so it can't "
                               "continue as one. Reject it or send it back to the vendor.")
    unknown = sorted(set(fields) - set(EDITABLE_FIELDS))
    if unknown:
        raise ReviewError(422, f"These fields can't be edited: {', '.join(unknown)}.")

    before = dict(row.extraction or ExtractedInvoice().model_dump(mode="json"))
    after = dict(before)
    changes = {}
    for field, raw in fields.items():
        value = _clean(field, raw)
        if value != before.get(field):
            changes[field] = {"label": FIELD_LABELS[field], "before": before.get(field), "after": value,
                              "before_display": None if before.get(field) is None else _money_text(field, before.get(field)),
                              "after_display": None if value is None else _money_text(field, value)}
        after[field] = value
    # A person has now checked every field, so nothing is left at low confidence.
    after["confidence"] = {k: ("high" if v == "low" else v) for k, v in (before.get("confidence") or {}).items()}
    try:
        inv = ExtractedInvoice.model_validate(after)
    except ValidationError as e:
        raise ReviewError(422, f"Those values don't form a valid invoice: {e.errors()[0]['msg']}.")

    extraction = inv.model_dump(mode="json")
    write_invoice_row(row, "invoice", extraction, inv)

    # Stage 2 now reflects the confirmed values: its "please confirm" hold is resolved.
    stage2 = next((s for s in stages if s.stage_order == 2), None)
    if stage2 is not None:
        kept = [f for f in (stage2.details or {}).get("findings", []) if not (f["code"] == "2.2" and f["severity"] == "hold")]
        what = f"{len(changes)} field(s) corrected" if changes else "values confirmed"
        stage2.status = "pass"
        stage2.message = f"{stage2.message.split(' · ')[0]} · {what} by {role}"
        stage2.details = {**(stage2.details or {}), "fields": extraction, "findings": kept, "reviewed_by": role}

    _rewind(db, row, keep_through=RESUME_AFTER_CONFIRM)
    _log(db, row.run_id, role, "confirm", None, changes)
    return Outcome(row.run_id, "confirm", row.status, resume_from=RESUME_AFTER_CONFIRM)


def pick_po(db: Session, row: Invoice, stages: list[RunStage], role: str, po_id: str | None) -> Outcome:
    po_id = _required(po_id, "PO number").upper()
    po = db.get(PurchaseOrder, po_id)
    if po is None:
        raise ReviewError(422, f"There's no PO called {po_id}.")
    if po.status != "Open":
        raise ReviewError(422, f"{po.po_id} is {po.status.lower()}, so no invoice can be paid against it.")
    if row.vendor_id and po.vendor_id != row.vendor_id:
        raise ReviewError(422, f"{po.po_id} was issued to {po.vendor.name}, not to this invoice's vendor.")
    if row.invoice_date and row.invoice_date < po.po_date:
        raise ReviewError(422, f"The invoice is dated {row.invoice_date:%d %b %Y}, before {po.po_id} was raised on "
                               f"{po.po_date:%d %b %Y}. Pick another PO, or send it to Procurement.")
    if not any(s.stage_order == RESUME_AFTER_PICK_PO for s in stages):
        raise ReviewError(409, "This run stopped before PO matching, so there's nothing to pick yet. "
                               "Confirm the invoice details first.")

    before = {"po_id": row.po_id, "po_match_type": row.po_match_type}
    stage5 = next(s for s in stages if s.stage_order == RESUME_AFTER_PICK_PO)
    picked = {"code": "5.1", "label": code_label("5.1"), "severity": "pass",
              "message": f"{po.po_id} was picked by the reviewer ({role}).", "audience": [], "fraud": False}
    stage5.status, stage5.message = "pass", f"Matched {po.po_id} (picked by {role})"
    stage5.details = {**(stage5.details or {}), "po_id": po.po_id, "picked_by": role, "findings": [picked]}

    _rewind(db, row, keep_through=RESUME_AFTER_PICK_PO)
    row.po_id, row.po_match_type, row.match_confidence = po.po_id, PICKED_MATCH_TYPE, "High"
    _log(db, row.run_id, role, "pick_po", None,
         {"po_id": {"label": "PO", "before": before["po_id"], "after": po.po_id},
          "po_match_type": {"label": "Match type", "before": before["po_match_type"], "after": PICKED_MATCH_TYPE}})
    return Outcome(row.run_id, "pick_po", row.status, resume_from=RESUME_AFTER_PICK_PO)


def _close(row: Invoice, decision: str, status: str) -> dict:
    before = {"decision": {"label": "Decision", "before": row.decision, "after": decision},
              "status": {"label": "Status", "before": row.status, "after": status}}
    row.decision, row.status = decision, status
    row.finished_at = row.finished_at or utcnow()
    return before


def override(db: Session, row: Invoice, stages: list[RunStage], role: str, reason: str | None) -> Outcome:
    reason = _required(reason, "reason for approving anyway")
    if _has_fraud(stages) and role != FINANCE_ROLE:
        raise ReviewError(403, "This invoice has a fraud finding. Only Finance can clear it, after verifying the "
                               "vendor by phone on the number on file.")
    changes = _close(row, "Approve", "approved")
    note = {"code": "review", "label": "Override", "severity": "pass", "message": f"Approved by {role}: {reason}",
            "audience": []}
    row.decision_reasons = [note, *(row.decision_reasons or [])]
    payee = row.vendor.name if row.vendor else "the vendor"
    by = f" by {row.due_date:%d %b %Y}" if row.due_date else ""
    _restamp_decision(_decision_stage(stages), "Approve", "approved", "pass",
                      f"Approved by {role} override. Pay {format_inr(row.total_paise)} to {payee}{by}.")
    alerts.discard_drafts(db, row.run_id)
    _log(db, row.run_id, role, "override", reason, changes)
    return Outcome(row.run_id, "override", row.status)


def reject(db: Session, row: Invoice, stages: list[RunStage], role: str, reason: str | None) -> Outcome:
    reason = _required(reason, "reason for rejecting")
    changes = _close(row, "Reject", "rejected")
    note = {"code": "review", "label": "Reviewer", "severity": "reject", "message": f"Rejected by {role}: {reason}",
            "audience": []}
    row.decision_reasons = [note, *(row.decision_reasons or [])]
    _restamp_decision(_decision_stage(stages), "Reject", "rejected", "fail", f"Rejected by {role}: {reason}")
    alerts.discard_drafts(db, row.run_id)
    _log(db, row.run_id, role, "reject", reason, changes)
    return Outcome(row.run_id, "reject", row.status)


def send_to_vendor(db: Session, row: Invoice, stages: list[RunStage], role: str, reasons: list[str] | None,
                   note: str | None, subject: str | None, body: str | None) -> Outcome:
    if _has_fraud(stages):
        raise ReviewError(409, "This invoice has a fraud finding, so nothing goes to the vendor. Finance verifies it "
                               "by phone on the number on file.")
    try:
        email = vendor_email.final_email(db, row, stages, reasons if reasons is not None else [], note, subject, body)
    except vendor_email.EmailError as e:
        raise ReviewError(e.status, e.message)
    changes = _close(row, row.decision or "Hold", "waiting_on_vendor")
    changes["email"] = {"label": "Email to vendor", **email}
    _restamp_decision(_decision_stage(stages), row.decision, "waiting_on_vendor", "warn",
                      f"Sent back to the vendor by {role}: {email['reasons_text']}.")
    alerts.discard_drafts(db, row.run_id)
    entry = _log(db, row.run_id, role, "send_to_vendor", email["reasons_text"], changes)
    db.commit()
    try:
        alert = alerts.send_back_to_vendor(db, row, email["subject"], email["body"], role)
    except alerts.VendorEmailBlocked as e:  # _has_fraud already checked; this is the last line of defence
        raise ReviewError(409, str(e))
    # History shows what went out: the live response link and the Ref in the subject.
    entry.field_changes = {**changes, "email": {**changes["email"], "subject": alert.subject, "body": alert.body}}
    return Outcome(row.run_id, "send_to_vendor", row.status)


def send_reminder(db: Session, row: Invoice, stages: list[RunStage], role: str) -> Outcome:
    if row.status != "waiting_on_vendor":
        raise ReviewError(409, "A reminder only goes out while the invoice is waiting on the vendor.")
    if _has_fraud(stages):
        raise ReviewError(409, "This invoice has a fraud finding, so nothing goes to the vendor. Finance verifies it "
                               "by phone on the number on file.")
    try:
        alert = alerts.send_reminder(db, row, role)
    except alerts.VendorEmailBlocked as e:
        raise ReviewError(409, str(e))
    except LookupError as e:
        raise ReviewError(409, str(e))
    _log(db, row.run_id, role, "send_reminder", "Reminder sent with a new response link",
         {"email": {"label": "Reminder to vendor", "subject": alert.subject, "body": alert.body}})
    return Outcome(row.run_id, "send_reminder", row.status)


def supersede(db: Session, row: Invoice, role: str | None, new_run_id: str) -> None:
    """A corrected invoice replaces this run: it leaves the queue, keeps its decision, and the change is logged.
    The caller commits it together with the new run."""
    role = (role or "").strip() or DEFAULT_ROLE
    if row.status not in REVIEWABLE:
        raise ReviewError(409, f"{row.run_id} is {row.status.replace('_', ' ')}, so it can't be replaced.")
    if _has_fraud(_stages(db, row.run_id)) and role != FINANCE_ROLE:
        raise ReviewError(403, "This invoice has a fraud finding. Only Finance can replace it, after verifying the "
                               "vendor by phone on the number on file.")
    changes = {"status": {"label": "Status", "before": row.status, "after": SUPERSEDED},
               "replaced_by": {"label": "Replaced by", "before": None, "after": new_run_id}}
    row.status = SUPERSEDED
    alerts.discard_drafts(db, row.run_id)
    _log(db, row.run_id, role, "upload_corrected", f"Corrected invoice uploaded as {new_run_id}", changes)


def email_preview(db: Session, run_id: str, reasons: list[str] | None = None, note: str | None = None) -> dict:
    row = db.get(Invoice, run_id)
    if row is None:
        raise ReviewError(404, f"Run {run_id} not found.")
    if row.status not in REVIEWABLE:
        raise ReviewError(409, f"{run_id} is {row.status.replace('_', ' ')}, so there's nothing to send.")
    try:
        return vendor_email.preview(db, row, _stages(db, run_id), reasons, note)
    except vendor_email.EmailError as e:
        raise ReviewError(e.status, e.message)


def apply(db: Session, run_id: str, action: str, role: str | None, *, fields: dict | None = None,
          po_id: str | None = None, reason: str | None = None, note: str | None = None,
          reasons: list[str] | None = None, subject: str | None = None, body: str | None = None) -> Outcome:
    role = (role or "").strip() or DEFAULT_ROLE
    row = db.get(Invoice, run_id)
    if row is None:
        raise ReviewError(404, f"Run {run_id} not found.")
    if action not in ACTIONS:
        raise ReviewError(422, f"Unknown action '{action}'. Use one of: {', '.join(ACTIONS)}.")
    if row.status not in REVIEWABLE:
        raise ReviewError(409, f"{run_id} is {row.status.replace('_', ' ')}, so there's nothing to review.")
    stages = _stages(db, run_id)
    if action == "confirm":
        out = confirm(db, row, stages, role, fields or {})
    elif action == "pick_po":
        out = pick_po(db, row, stages, role, po_id)
    elif action == "override":
        out = override(db, row, stages, role, reason)
    elif action == "reject":
        out = reject(db, row, stages, role, reason)
    elif action == "send_reminder":
        out = send_reminder(db, row, stages, role)
    else:
        out = send_to_vendor(db, row, stages, role, reasons, note, subject, body)
    if out.resume_from is not None:
        alerts.discard_drafts(db, run_id)
    db.commit()
    return out
