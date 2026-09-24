"""Alerts: one email per audience per run, from templates, sent through Resend (build guide section 10).

Every email goes to OWNER_EMAIL; who it was meant for is stored on the alert and printed at the top.
Vendor emails are never built or sent when the run has a fraud finding.
A vendor email for a Hold carries a single-use response link (a token on the alert); a newer email replaces it.
A failed send marks the alert Failed and never fails the run.
"""

import logging
import re
import secrets
from datetime import datetime, timedelta

import resend
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Alert, CompanySettings, Invoice, RunStage, Vendor, clip, utcnow
from app.pipeline.context import Finding, RunContext
from app.utils.money import format_inr
from app.utils.timefmt import as_utc, iso

log = logging.getLogger(__name__)

AUDIENCE_ORDER = ["Finance", "AP", "Procurement", "Vendor"]
TOKEN_DAYS = 7
REMINDER = "Reminder: "


class VendorEmailBlocked(Exception):
    """A vendor email was asked for on a run with a fraud finding."""


# --- Names --------------------------------------------------------------------------------------------------------

_COMPANY_SUFFIX = re.compile(r"\s+(pvt\.?|private|ltd\.?|limited|llp|inc\.?)(\s+.*)?$", re.IGNORECASE)


def company_short(company: CompanySettings | None) -> str:
    """'Nimbus Retail Pvt Ltd' → 'Nimbus Retail'."""
    name = company.name if company else "Our company"
    return _COMPANY_SUFFIX.sub("", name).strip() or name


def vendor_names(vendor: Vendor | None, printed: str | None) -> tuple[str, str]:
    """(full name, short name) for the vendor, from the master if known, else as printed."""
    if vendor is not None:
        return vendor.name, vendor.short_name or vendor.name
    name = printed or "the vendor"
    return name, name


def intended_for(audience: str, company: CompanySettings | None, vendor_full: str) -> str:
    us = company_short(company)
    return {
        "Vendor": f"{vendor_full} (accounts)",
        "AP": f"{us} AP team",
        "Procurement": f"{us} Procurement",
        "Finance": f"{us} Finance",
    }.get(audience, f"{us} {audience}")


def subject_prefix(audience: str, vendor_short: str, fraud: bool) -> str:
    if audience == "Vendor":
        return f"[InvoiceIQ → Vendor: {vendor_short}]"
    if audience == "Finance" and fraud:
        return "[InvoiceIQ → Finance · Fraud check]"
    return f"[InvoiceIQ → {audience}]"


# --- The facts every template uses -----------------------------------------------------------------------------------

class Facts:
    """What the templates say about one run, read once."""

    def __init__(self, row: Invoice, company: CompanySettings | None, vendor: Vendor | None,
                 po_id: str | None):
        ex = row.extraction or {}
        self.run_id = row.run_id
        self.company = company
        self.vendor = vendor
        self.vendor_full, self.vendor_short = vendor_names(vendor, ex.get("vendor_name"))
        self.invoice_no = row.invoice_no or ex.get("invoice_number")
        self.invoice_date = row.invoice_date
        self.total = format_inr(row.total_paise) if row.total_paise is not None else None
        self.po_id = po_id

    @property
    def invoice_ref(self) -> str:
        return f"invoice {self.invoice_no}" if self.invoice_no else "your invoice (no invoice number)"

    @property
    def dated(self) -> str:
        return f" dated {self.invoice_date:%d %b %Y}" if self.invoice_date else ""

    def summary(self) -> str:
        """'BT/26/0917 (₹2,47,800, PO-2026-116, BrightTech Solutions)'."""
        bits = [b for b in (self.total, self.po_id, self.vendor_short) if b]
        no = self.invoice_no or "without a number"
        return f"{no} ({', '.join(bits)})" if bits else no


def facts_for(ctx: RunContext) -> Facts:
    return Facts(ctx.db.get(Invoice, ctx.run_id), ctx.company, ctx.vendor, ctx.po.po_id if ctx.po else None)


def _numbered(lines: list[str]) -> str:
    return "\n".join(f"  {i}. {line}" for i, line in enumerate(lines, start=1))


def review_url(run_id: str) -> str:
    return f"{settings.BASE_URL.rstrip('/')}/review/{run_id}"


def run_url(run_id: str) -> str:
    return f"{settings.BASE_URL.rstrip('/')}/process?run={run_id}"


def respond_url(token: str) -> str:
    return f"{settings.BASE_URL.rstrip('/')}/respond/{token}"


# --- The vendor's response link ---------------------------------------------------------------------------------------

LINK_PENDING = "<link-created-when-sent>"  # stands in for the token in a preview; replaced when the email goes out
_LINK_LINE = re.compile(r"Upload your corrected invoice here \(link valid until [^)]*\): \S+")


def response_paragraph(url: str, expires: datetime) -> str:
    return (f"Upload your corrected invoice here (link valid until {expires:%d %b %Y}): {url}. "
            "You can also reply to this email with the PDF attached.")


def pending_link() -> tuple[str, datetime]:
    """What a preview shows: the real expiry date, and a placeholder where the token will go."""
    return respond_url(LINK_PENDING), utcnow() + timedelta(days=TOKEN_DAYS)


def with_response_link(body: str, url: str, expires: datetime) -> str:
    """Put the live link in the body: over the placeholder (or an older link), or before the sign-off if a reviewer
    deleted it."""
    line = response_paragraph(url, expires)
    first = line.split(" You can also")[0]
    if _LINK_LINE.search(body):
        return _LINK_LINE.sub(lambda _: first, body, count=1)
    if "\n\nThank you," in body:
        head, tail = body.rsplit("\n\nThank you,", 1)
        return f"{head}\n\n{line}\n\nThank you,{tail}"
    return f"{body.rstrip()}\n\n{line}"


def with_ref(subject_line: str, run_id: str) -> str:
    """Vendor subjects end with 'Ref RUN-…' so a reply by email can be matched to its run."""
    return subject_line if run_id in subject_line else f"{subject_line} · Ref {run_id}"


def issue_token(db: Session, alert: Alert) -> None:
    """A fresh response link on a vendor Hold email, valid for TOKEN_DAYS. Older links on the run stop working:
    one active link per run."""
    now = utcnow()
    for old in db.scalars(select(Alert).where(Alert.run_id == alert.run_id, Alert.response_token.is_not(None))):
        if old is not alert and old.token_expires is not None and as_utc(old.token_expires) > now:
            old.token_expires = now
    alert.response_token = secrets.token_urlsafe(32)
    alert.token_expires = now + timedelta(days=TOKEN_DAYS)
    alert.token_used_at = None
    alert.body = with_response_link(alert.body, respond_url(alert.response_token), alert.token_expires)


# --- Templates (no LLM) ---------------------------------------------------------------------------------------------

def vendor_body(f: Facts, decision: str, findings: list[Finding], reason: str | None = None,
                note: str | None = None, link: tuple[str, datetime] | None = None) -> str:
    """`link` is (url, expiry) for a Hold; without one the vendor is asked to reply by email."""
    against = f" against {f.po_id}" if f.po_id else ""
    amount = f" for {f.total}" if f.total else ""
    closing = "We can't accept it because:" if decision == "Reject" else "We can't process it yet because:"
    parts = [
        f"Intended for: {f.vendor_full} (accounts)",
        f"Hello {f.vendor_short} team,",
        f"We've received {f.invoice_ref}{f.dated}{amount}{against}.\n{closing}",
    ]
    issues = ([f"{reason}."] if reason else []) + [x.message for x in findings]
    if issues:
        parts.append(_numbered(issues))
    if note:
        parts.append("Note from our AP team:\n" + "\n".join(f"  {line}" for line in note.splitlines() if line.strip()))
    if decision == "Reject":
        parts.append("Please don't resend this document. If you believe this is a mistake, reply to your usual "
                     "contact in our AP team.")
    elif link is not None:
        parts.append(response_paragraph(*link))
    else:
        parts.append("Please reply with a corrected invoice.")
    parts.append(f"Thank you,\nAccounts Payable, {f.company.name if f.company else 'our company'}")
    return "\n\n".join(parts)


def finance_fraud_body(f: Facts, findings: list[Finding]) -> str:
    fraud = [x for x in findings if x.fraud]
    others = [x for x in findings if not x.fraud]
    phone = f.vendor.phone if f.vendor is not None and f.vendor.phone else None
    call = (f"Verify the change by calling {f.vendor_short} on {phone}, the number in the vendor master."
            if phone else f"Verify the change by calling {f.vendor_short} on the phone number in the vendor master.")
    parts = [
        f"Intended for: {intended_for('Finance', f.company, f.vendor_full)}",
        f"Possible payment fraud on invoice {f.summary()}.",
        _numbered([x.message for x in fraud]),
    ]
    if others:
        parts.append("Also on this invoice:\n" + _numbered([x.message for x in others]))
    parts.append(f"Do not reply to the email that sent this invoice. {call} Clear or reject this hold in InvoiceIQ:\n"
                 f"{review_url(f.run_id)}")
    return "\n\n".join(parts)


def internal_body(f: Facts, audience: str, decision: str, headline: str, findings: list[Finding]) -> str:
    link = review_url(f.run_id) if decision == "Hold" else run_url(f.run_id)
    action = "Review it in InvoiceIQ" if decision == "Hold" else "Open it in InvoiceIQ"
    return "\n\n".join([
        f"Intended for: {intended_for(audience, f.company, f.vendor_full)}",
        f"Invoice {f.summary()}.\n{headline}",
        "For your team:\n" + _numbered([x.message for x in findings]),
        f"{action}:\n{link}",
    ])


def subject(audience: str, f: Facts, decision: str, fraud: bool) -> str:
    prefix = subject_prefix(audience, f.vendor_short, fraud)
    no = f.invoice_no or "without a number"
    if audience == "Vendor":
        what = "can't be accepted" if decision == "Reject" else "needs a correction"
        return with_ref(f"{prefix} Invoice {no} {what}", f.run_id)
    if audience == "Finance" and fraud:
        return f"{prefix} Verify {f.vendor_short} before paying invoice {no}"
    word = {"Approve": "Approved", "Hold": "On hold", "Reject": "Rejected"}.get(decision, decision)
    return f"{prefix} {word}: invoice {no} from {f.vendor_short}"


# --- Build and send -------------------------------------------------------------------------------------------------

def _new_alert(run_id: str, audience: str, facts: Facts, subj: str, body: str) -> Alert:
    return Alert(
        run_id=run_id,
        audience=audience,
        intended_for=clip(Alert, "intended_for", intended_for(audience, facts.company, facts.vendor_full)),
        to_email=settings.OWNER_EMAIL,
        subject=clip(Alert, "subject", subj),
        body=body,
        status="Drafted",
    )


def build_alerts(ctx: RunContext, decision: str, audiences: dict[str, list[Finding]], headline: str) -> list[Alert]:
    """One Alert per audience. `audiences` comes from decide.alert_audiences, which already drops the vendor on fraud."""
    fraud = any(f.fraud for f in ctx.findings)
    facts = facts_for(ctx)
    out = []
    for audience in sorted(audiences, key=lambda a: AUDIENCE_ORDER.index(a) if a in AUDIENCE_ORDER else 99):
        findings = audiences[audience]
        if audience == "Vendor":
            if fraud:  # belt and braces: never a vendor email on a fraud run
                continue
            link = pending_link() if decision == "Hold" else None  # never a response link on a Reject
            alert = _new_alert(ctx.run_id, audience, facts, subject(audience, facts, decision, fraud),
                               vendor_body(facts, decision, findings, link=link))
            if link is not None:
                issue_token(ctx.db, alert)
        elif audience == "Finance" and fraud:
            alert = _new_alert(ctx.run_id, audience, facts, subject(audience, facts, decision, fraud),
                               finance_fraud_body(facts, findings))
        else:
            alert = _new_alert(ctx.run_id, audience, facts, subject(audience, facts, decision, fraud),
                               internal_body(facts, audience, decision, headline, findings))
        out.append(alert)
    return out


def _send_email(subject_line: str, body: str) -> str | None:
    """The one place that talks to Resend. Tests replace it."""
    if not settings.RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY isn't set")
    resend.api_key = settings.RESEND_API_KEY
    # Replies (a vendor answering with the PDF attached) come back to the owner's inbox too.
    resp = resend.Emails.send({"from": settings.EMAIL_FROM, "to": [settings.OWNER_EMAIL],
                               "reply_to": settings.OWNER_EMAIL, "subject": subject_line, "text": body})
    return resp.get("id") if isinstance(resp, dict) else getattr(resp, "id", None)


def deliver(alert: Alert) -> None:
    """Send now. Sent on success, Failed on any error; never raises."""
    if not settings.SEND_EMAILS:
        log.info("SEND_EMAILS is off; alert for %s stays Drafted", alert.audience)
        return
    try:
        email_id = _send_email(alert.subject, alert.body)
    except Exception as e:
        alert.status = "Failed"
        log.warning("Resend failed for %s alert on %s: %s", alert.audience, alert.run_id, type(e).__name__)
        return
    alert.status, alert.sent_at = "Sent", utcnow()
    log.info("Sent %s alert for %s (Resend id %s)", alert.audience, alert.run_id, email_id)


def auto_send(alert: Alert, company: CompanySettings | None) -> bool:
    """Internal alerts always send. Vendor ones only when auto-send is on in Settings and not switched off for the
    deployment (VENDOR_AUTO_SEND); otherwise they wait in the Outbox for AP to press Send."""
    if alert.audience != "Vendor":
        return True
    return settings.VENDOR_AUTO_SEND and (company.vendor_auto_send if company is not None else True)


def build_and_send(ctx: RunContext, decision: str, audiences: dict[str, list[Finding]], headline: str) -> list[Alert]:
    """Called from the decision step. Stores every alert first, then sends. Never fails the run."""
    try:
        alerts = build_alerts(ctx, decision, audiences, headline)
        ctx.db.add_all(alerts)
        ctx.db.commit()
        for alert in alerts:
            if ctx.send_emails and auto_send(alert, ctx.company):
                deliver(alert)
                ctx.db.commit()
        return alerts
    except Exception:
        log.exception("Building alerts for %s failed", ctx.run_id)
        ctx.db.rollback()
        return []


# --- Used by review and the Outbox ----------------------------------------------------------------------------------

def run_has_fraud(db: Session, run_id: str) -> bool:
    stages = db.scalars(select(RunStage).where(RunStage.run_id == run_id))
    return any(f.get("fraud") for s in stages for f in (s.details or {}).get("findings", []))


def send_drafted(db: Session, alert: Alert) -> Alert:
    """Outbox 'Send': a Drafted alert (or a Failed one, as a retry)."""
    if alert.audience == "Vendor" and run_has_fraud(db, alert.run_id):
        raise VendorEmailBlocked("This invoice has a fraud finding, so nothing can be sent to the vendor.")
    if alert.response_token is not None:  # it may have waited in the Outbox: the link runs 7 days from sending
        issue_token(db, alert)
    deliver(alert)
    db.commit()
    return alert


def discard_drafts(db: Session, run_id: str) -> int:
    """A reviewer acted, so unsent drafts from the earlier decision are out of date. A draft whose response link the
    vendor already used stays: it's the record that link reached them."""
    drafts = db.scalars(select(Alert).where(Alert.run_id == run_id, Alert.status == "Drafted",
                                            Alert.token_used_at.is_(None))).all()
    for a in drafts:
        db.delete(a)
    return len(drafts)


def send_back_to_vendor(db: Session, row: Invoice, subject_line: str, body: str, reviewer: str) -> Alert:
    """Reviewer's 'Send to vendor': the email they checked and maybe edited, sent now (the reviewer is the approval)."""
    if run_has_fraud(db, row.run_id):
        raise VendorEmailBlocked("This invoice has a fraud finding, so nothing can be sent to the vendor. "
                                 "Finance verifies it by phone instead.")
    company = db.scalar(select(CompanySettings).limit(1))
    facts = Facts(row, company, row.vendor, row.po_id)
    alert = _new_alert(row.run_id, "Vendor", facts, clip(Alert, "subject", with_ref(subject_line, row.run_id)), body)
    if row.decision != "Reject":
        issue_token(db, alert)
    db.add(alert)
    db.commit()
    deliver(alert)
    db.commit()
    log.info("%s sent %s back to the vendor", reviewer, row.run_id)
    return alert


def last_vendor_email(db: Session, run_id: str) -> Alert | None:
    return db.scalar(select(Alert).where(Alert.run_id == run_id, Alert.audience == "Vendor")
                     .order_by(Alert.alert_id.desc()).limit(1))


def send_reminder(db: Session, row: Invoice, reviewer: str) -> Alert:
    """The last vendor email again, with 'Reminder:' in front and a fresh link (the old one stops working)."""
    if run_has_fraud(db, row.run_id):
        raise VendorEmailBlocked("This invoice has a fraud finding, so nothing can be sent to the vendor. "
                                 "Finance verifies it by phone instead.")
    last = last_vendor_email(db, row.run_id)
    if last is None:
        raise LookupError("Nothing has been sent to the vendor yet, so there's nothing to remind them of.")
    subject_line = last.subject if last.subject.startswith(REMINDER) else f"{REMINDER}{last.subject}"
    alert = Alert(run_id=row.run_id, audience="Vendor", intended_for=last.intended_for, to_email=settings.OWNER_EMAIL,
                  subject=clip(Alert, "subject", with_ref(subject_line, row.run_id)), body=last.body, status="Drafted")
    issue_token(db, alert)
    db.add(alert)
    db.commit()
    deliver(alert)
    db.commit()
    log.info("%s reminded the vendor about %s", reviewer, row.run_id)
    return alert


def vendor_responded(db: Session, original: Invoice, new_run_id: str, message: str | None) -> Alert:
    """Tell AP a corrected invoice came in through the response link. Stored, then sent now."""
    company = db.scalar(select(CompanySettings).limit(1))
    facts = Facts(original, company, original.vendor, original.po_id)
    parts = [
        f"Intended for: {intended_for('AP', company, facts.vendor_full)}",
        f"{facts.vendor_short} sent a corrected invoice for {facts.invoice_no or 'an invoice without a number'}"
        f"{' (' + ', '.join(b for b in (facts.total, facts.po_id) if b) + ')' if facts.total or facts.po_id else ''}"
        " through the response link.",
    ]
    if message:
        parts.append("Their message:\n" + "\n".join(f"  {line}" for line in message.splitlines() if line.strip()))
    parts.append(f"It replaces {original.run_id} and is being checked now. Follow it in InvoiceIQ:\n{run_url(new_run_id)}")
    alert = _new_alert(original.run_id, "AP", facts,
                       f"{subject_prefix('AP', facts.vendor_short, False)} Vendor sent a corrected invoice for "
                       f"{facts.invoice_no or 'an invoice without a number'} from {facts.vendor_short}",
                       "\n\n".join(parts))
    db.add(alert)
    db.commit()
    deliver(alert)
    db.commit()
    return alert


def alert_dict(a: Alert, row: Invoice | None = None) -> dict:
    return {
        "alert_id": a.alert_id,
        "run_id": a.run_id,
        "audience": a.audience,
        "intended_for": a.intended_for,
        "to_email": a.to_email,
        "subject": a.subject,
        "body": a.body,
        "status": a.status,
        "sent_at": iso(a.sent_at),
        "invoice_no": row.invoice_no if row is not None else None,
        "run_status": row.status if row is not None else None,
    }
