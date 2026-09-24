"""Stage 9: dates and payment terms (cases 9.1-9.5)."""

from datetime import timedelta

from app.config import DEFAULT_TERMS_DAYS, MSME_MAX_TERMS_DAYS, STALE_INVOICE_DAYS
from app.pipeline.context import RunContext, StageResult, summarise


def run(ctx: RunContext) -> StageResult:
    inv, po, vendor = ctx.inv, ctx.po, ctx.vendor
    if inv.invoice_date is None:
        return StageResult("info", "Skipped: no invoice date, so no due date can be set", {})
    before = len(ctx.findings)

    terms = po.payment_terms_days if po else DEFAULT_TERMS_DAYS
    source = f"{po.po_id} terms" if po else "default terms (no PO matched)"
    details = {"terms_days": terms, "terms_source": source}
    if vendor is not None and vendor.msme and terms > MSME_MAX_TERMS_DAYS:
        ctx.add("9.5", "info", f"{vendor.name} is an MSME, so the due date is capped at {MSME_MAX_TERMS_DAYS} days "
                               f"(the terms say {terms}).", [], {"terms_days": terms, "capped_at": MSME_MAX_TERMS_DAYS})
        terms = MSME_MAX_TERMS_DAYS
        details["msme_cap"] = MSME_MAX_TERMS_DAYS

    due = inv.invoice_date + timedelta(days=terms)
    ctx.due_date = due
    details["due_date"] = due.isoformat()

    age = (ctx.today - inv.invoice_date).days
    if age > STALE_INVOICE_DAYS:
        ctx.add("9.2", "hold", f"The invoice is {age} days old (dated {inv.invoice_date:%d %b %Y}), over the "
                               f"{STALE_INVOICE_DAYS}-day limit.", ["AP"], {"age_days": age})
    if inv.payment_terms_days is not None and po and inv.payment_terms_days != po.payment_terms_days:
        ctx.add("9.3", "info", f"The invoice says {inv.payment_terms_days} days; the PO terms "
                               f"({po.payment_terms_days} days) apply.", [])
    if due < ctx.today:
        ctx.add("9.4", "info", f"Already overdue (due {due:%d %b %Y}): pay urgently.", ["AP"])
    ctx.add("9.1", "pass", f"Due {due:%d %b %Y}, {terms} days after the invoice date.", [], details)

    holds = [f for f in ctx.findings[before:] if f.severity == "hold"]
    if holds:
        return StageResult("warn", summarise(holds), details)
    return StageResult("pass", f"Due {due:%d %b %Y} ({terms} days)", details)
