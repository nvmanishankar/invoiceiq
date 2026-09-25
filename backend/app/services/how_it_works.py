"""Data for the "How it works" page: the case catalogue, a real PO-matching walkthrough, the GST rate history,
the vendor loop for sample 04, and the facts part B quotes (who may do what, limits, test counts).

The walkthroughs run a sample through the real pipeline on a scratch copy of the seed data (like the test suite),
offline from the committed fixtures, so their numbers are whatever the code produces today, never copied from a doc.
tests/test_how_it_works.py calls every guarded endpoint as each role to keep PERMISSIONS honest.
"""

import threading
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import alerts, config, llm, seed
from app.config import settings
from app.db import make_engine
from app.models import Alert, PurchaseOrder, RunStage, TaxRate
from app.pipeline.catalogue import catalogue
from app.pipeline.runner import create_run, file_hash, run_pipeline
from app.services import company, purchasing, respond, review, stats, test_suite
from app.services import runs as run_service
from app.services.po import po_remaining_paise, po_total_paise
from app.services.purchasing import rate_dict
from app.utils.money import format_inr

WALKTHROUGH_SAMPLE = "03_edge_inferred_po_acme.pdf"
VENDOR_LOOP_SAMPLE = "04_edge_split_overbill_acme.pdf"
PO_STAGE = 5
AMOUNTS_STAGE = 6

# `pytest -q` in backend/, including the test that checks this number (tests/test_how_it_works.py).
AUTOMATED_TESTS = 409

# Who may do what, as the server enforces it. `rule`:
#   anyone       no role check
#   procurement  roles.require_procurement: 403 for anyone else
#   finance      roles.require_finance: 403 for anyone else
# `fraud` is what changes on an invoice with a fraud finding (4.6, 4.7):
#   finance      only Finance may do it (review.py: 403 for anyone else)
#   nobody       refused for every role (review.py / alerts.py: 409)
PERMISSIONS = [
    {"key": "upload", "area": "Process", "action": "Upload an invoice or run a sample", "rule": "anyone",
     "why": f"Anyone can start a run. New files the AI has to read are capped at {settings.MAX_RUNS_PER_DAY} a day "
            "for the whole demo; samples and files read before don't count.",
     "where": "routers/runs.py"},
    {"key": "confirm", "area": "Review", "action": "Confirm and continue", "rule": "anyone",
     "why": "Correcting a misread field isn't limited by role.", "where": "services/review.py"},
    {"key": "pick_po", "area": "Review", "action": "Pick PO", "rule": "anyone",
     "why": "Choosing the PO isn't limited by role; the PO must still be open, the vendor's, and dated on or before "
            "the invoice.", "where": "services/review.py"},
    {"key": "override", "area": "Review", "action": "Override and approve", "rule": "anyone", "fraud": "finance",
     "why": "Any role may approve anyway with a written reason, which is logged.",
     "fraud_why": "Only Finance can clear a fraud hold, after calling the vendor on the number on file.",
     "where": "services/review.py"},
    {"key": "send_to_vendor", "area": "Review", "action": "Send to vendor", "rule": "anyone", "fraud": "nobody",
     "why": "Any role may send the vendor the checked email.",
     "fraud_why": "Nothing goes to the vendor on a fraud hold, whoever asks.", "where": "services/review.py"},
    {"key": "send_reminder", "area": "Review", "action": "Send reminder", "rule": "anyone", "fraud": "nobody",
     "why": "Any role may remind a vendor who hasn't replied.",
     "fraud_why": "Nothing goes to the vendor on a fraud hold, whoever asks.", "where": "services/review.py"},
    {"key": "corrected", "area": "Review", "action": "Upload corrected invoice", "rule": "anyone", "fraud": "finance",
     "why": "Any role may upload the vendor's corrected PDF.",
     "fraud_why": "Only Finance can replace an invoice with a fraud finding.", "where": "services/review.py"},
    {"key": "reject", "area": "Review", "action": "Reject", "rule": "anyone",
     "why": "Any role may reject with a written reason, which is logged.", "where": "services/review.py"},
    {"key": "outbox_send", "area": "Outbox", "action": "Send or retry an email", "rule": "anyone", "fraud": "nobody",
     "why": "Any role may send a drafted email or retry a failed one.",
     "fraud_why": "A vendor email on a fraud hold can't be sent from the Outbox either.", "where": "routers/alerts.py"},
    {"key": "create_po", "area": "Purchase orders", "action": "Raise a PO", "rule": "procurement",
     "why": "Whoever raises a PO must not also approve invoices against it.", "where": "routers/pos.py"},
    {"key": "po_status", "area": "Purchase orders", "action": "Close or reopen a PO", "rule": "procurement",
     "why": "Closing a PO changes what can be paid, so it stays with Procurement.", "where": "routers/pos.py"},
    {"key": "add_vendor", "area": "Vendors", "action": "Add a vendor", "rule": "procurement",
     "why": "Whoever approves invoices must not also be able to create the vendor being paid.",
     "where": "routers/vendors.py"},
    {"key": "vendor_status", "area": "Vendors", "action": "Block or unblock a vendor", "rule": "procurement",
     "why": "The vendor list is master data, owned by Procurement.", "where": "routers/vendors.py"},
    {"key": "tolerance", "area": "Settings", "action": "Change the tolerance", "rule": "finance",
     "why": "How far an invoice may differ from its PO is a financial control, so Finance owns it.",
     "where": "routers/settings.py"},
    {"key": "auto_send", "area": "Settings", "action": "Switch vendor auto-send on or off", "rule": "anyone",
     "why": "Not limited by role.", "where": "routers/settings.py"},
    {"key": "reset", "area": "Settings", "action": "Reset demo data", "rule": "anyone",
     "why": "Not limited by role; you must type RESET to confirm.", "where": "routers/admin.py"},
    {"key": "test_suite", "area": "Tests", "action": "Run the test suite", "rule": "anyone",
     "why": "Runs on a scratch copy, so it can't change live data.", "where": "routers/admin.py"},
]

_lock = threading.Lock()


def cases() -> dict:
    return catalogue()


def _po_row(db: Session, po: PurchaseOrder, run_id: str) -> dict:
    return {"po_id": po.po_id, "vendor": po.vendor.name, "status": po.status, "po_date": po.po_date.isoformat(),
            "total_paise": po_total_paise(po), "remaining_paise": po_remaining_paise(db, po, exclude_run=run_id),
            "lines": [{"description": ln.description, "qty": ln.qty, "unit_price_paise": ln.unit_price_paise}
                      for ln in po.lines]}


def _scratch(sample: str, use) -> dict:
    """Run `sample` offline on a scratch copy of the seed data and return `use(db, ctx)`. No emails, no quota."""
    data = (run_service.SAMPLES_DIR / sample).read_bytes()
    if llm.load_cache(file_hash(data)) is None:  # never spend quota on an explainer
        raise LookupError(f"{sample} has no cached extraction.")
    engine = make_engine("sqlite://")
    try:
        seed.reset(engine)
        with Session(engine, autoflush=False, expire_on_commit=False) as db:
            ctx = create_run(db, data, sample, today=run_service.today())
            ctx.offline, ctx.send_emails = True, False
            run_pipeline(ctx, min_stage_ms=0)
            return use(db, ctx)
    finally:
        engine.dispose()


@lru_cache(maxsize=1)
def _walkthrough() -> dict:
    def use(db: Session, ctx) -> dict:
        stage = db.scalars(select(RunStage).where(RunStage.run_id == ctx.run_id,
                                                  RunStage.stage_order == PO_STAGE)).one()
        d = stage.details or {}
        pos = {po.po_id: _po_row(db, po, ctx.run_id) for po in db.scalars(select(PurchaseOrder))}
        inv = ctx.inv
        return {
            "sample": WALKTHROUGH_SAMPLE,
            "invoice": {
                "vendor": ctx.vendor.name if ctx.vendor else inv.vendor_name,
                "invoice_no": inv.invoice_no,
                "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
                "total_paise": inv.total_paise,
                "po_reference": inv.po_reference,
                "lines": [{"description": ln.description, "qty": ln.qty, "unit_price_paise": ln.unit_price_paise}
                          for ln in inv.lines],
            },
            "elimination": [{**row, "po": pos.get(row["po_id"])} for row in d.get("elimination", [])],
            "scores": d.get("scores", []),
            "top": d.get("top"),
            "gap": d.get("gap"),
            "explanation": d.get("explanation"),
            "similarity_source": d.get("similarity_source"),
            "matched_po": ctx.po.po_id if ctx.po else None,
            "match_type": ctx.match_type,
            "match_confidence": ctx.match_confidence,
            "decision": ctx.decision,
            "stage_message": stage.message,
            "rules": catalogue()["rules"],
        }
    return _scratch(WALKTHROUGH_SAMPLE, use)


def po_walkthrough() -> dict:
    """Stage 5 of sample 03, run once per process: the pipeline is deterministic on fixtures and seed data."""
    with _lock:
        return _walkthrough()


@lru_cache(maxsize=1)
def _vendor_loop() -> dict:
    def use(db: Session, ctx) -> dict:
        email = review.email_preview(db, ctx.run_id)  # the reviewer's autofilled Send to vendor, nothing sent
        auto = db.scalar(select(Alert).where(Alert.run_id == ctx.run_id, Alert.audience == "Vendor",
                                             Alert.response_token.is_not(None)))
        page = respond.view(db, auto.response_token) if auto is not None else None
        stage6 = db.scalars(select(RunStage).where(RunStage.run_id == ctx.run_id,
                                                   RunStage.stage_order == AMOUNTS_STAGE)).one()
        remaining = (stage6.details or {}).get("remaining_paise")
        facts = stats.RunFacts(ctx.run_id, "needs_review", ctx.decision, ctx.inv.total_paise, None, None, None, None,
                               findings=[{"code": f.code, "fraud": f.fraud} for f in ctx.findings],
                               remaining_paise=remaining)
        protected = stats.protected_paise(facts)
        return {
            "sample": VENDOR_LOOP_SAMPLE,
            "run_id": ctx.run_id,
            "decision": ctx.decision,
            "findings": [{"code": f.code, "severity": f.severity, "message": f.message, "audience": f.audience}
                         for f in ctx.findings if f.severity in ("hold", "reject")],
            "email": {k: email[k] for k in ("subject", "body", "intended_for", "reasons", "note")},
            "response_page": page,
            "total_paise": ctx.inv.total_paise,
            "remaining_paise": remaining,
            "protected": {"category": protected[0], "paise": protected[1], "display": format_inr(protected[1])}
            if protected else None,
        }
    return _scratch(VENDOR_LOOP_SAMPLE, use)


def vendor_loop() -> dict:
    """Sample 04 held for over-billing: the Send to vendor email as a reviewer first sees it, and the vendor's page."""
    with _lock:
        return _vendor_loop()


def facts() -> dict:
    """Constants and limits the page quotes, read from the code that enforces them."""
    return {
        "permissions": PERMISSIONS,
        "roles": ["Procurement", "AP clerk", "Finance"],
        "resume": {"confirm": review.RESUME_AFTER_CONFIRM + 1, "pick_po": review.RESUME_AFTER_PICK_PO + 1},
        "token_days": alerts.TOKEN_DAYS,
        "max_runs_per_day": settings.MAX_RUNS_PER_DAY,
        "min_stage_ms": settings.MIN_STAGE_MS,
        "max_llm_calls": config.MAX_LLM_CALLS_PER_RUN,
        "max_upload_mb": run_service.MAX_UPLOAD_BYTES // (1024 * 1024),
        "minutes_saved_per_invoice": stats.MINUTES_SAVED_PER_INVOICE,
        "top_reasons": stats.TOP_REASONS,
        "msme_max_terms_days": config.MSME_MAX_TERMS_DAYS,
        "max_terms_days": purchasing.MAX_TERMS_DAYS,
        "first_new_po": purchasing.FIRST_NEW_PO,
        "max_tolerance_pct": company.MAX_TOLERANCE_PCT,
        "max_tolerance_cap_paise": company.MAX_TOLERANCE_CAP_RUPEES * 100,
        "suite_cooldown_seconds": test_suite.COOLDOWN_SECONDS,
        "tests": {"samples": len(test_suite.expected_samples()), "automated": AUTOMATED_TESTS},
    }


def tax_rates(db: Session, country: str = "IN") -> list[dict]:
    """Every GST rate with its dates, ended ones included, for the timeline."""
    rows = db.scalars(select(TaxRate).where(TaxRate.country == country).order_by(TaxRate.rate, TaxRate.valid_from))
    return [rate_dict(r) for r in rows]
