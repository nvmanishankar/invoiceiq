"""Decision: rules over the findings of every stage (build guide section 9, 'Decision').

Precedence: any reject → Reject; else any hold → Hold; else Approve.
Alerts are grouped here (one per audience); building and sending them is alerts.py's job.
"""

from collections import defaultdict

from app import alerts
from app.models import Invoice
from app.pipeline import s6_amounts
from app.pipeline.context import Finding, RunContext, StageResult
from app.services.po import lock_po
from app.utils.money import format_inr

STATUS = {"Reject": "rejected", "Hold": "needs_review", "Approve": "approved"}
STAGE_STATUS = {"Reject": "fail", "Hold": "warn", "Approve": "pass"}


def decide(findings: list[Finding]) -> str:
    severities = {f.severity for f in findings}
    return "Reject" if "reject" in severities else "Hold" if "hold" in severities else "Approve"


def alert_audiences(findings: list[Finding]) -> dict[str, list[Finding]]:
    """One alert per audience listing every finding for it. Fraud removes the vendor entirely."""
    by_audience: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        for a in f.audience:
            by_audience[a].append(f)
    if any(f.fraud for f in findings):
        by_audience.pop("Vendor", None)
    return dict(by_audience)


def _reason(f: Finding) -> dict:
    return {"code": f.code, "label": f.label, "severity": f.severity, "message": f.message, "audience": f.audience}


def reasons(findings: list[Finding], decision: str) -> list[dict]:
    if decision == "Approve":
        return [_reason(f) for f in findings if f.severity == "pass"]
    return [_reason(f) for f in findings if f.severity == "reject"] + \
           [_reason(f) for f in findings if f.severity == "hold"]


def headline(ctx: RunContext, decision: str, why: list[dict]) -> str:
    if decision == "Approve":
        payee = ctx.vendor.name if ctx.vendor else "the vendor"
        by = f" by {ctx.due_date:%d %b %Y}" if ctx.due_date else ""
        return f"Pay {format_inr(ctx.inv.total_paise)} to {payee}{by}."
    if decision == "Hold":
        return f"On hold: {len(why)} issue(s) need attention."
    return f"Rejected: {why[0]['message']}"


def save_decision(ctx: RunContext, decision: str, why: list[dict]) -> None:
    row = ctx.db.get(Invoice, ctx.run_id)
    if row is None:
        return
    row.decision = decision
    row.status = STATUS[decision]
    row.decision_reasons = why
    row.due_date = ctx.due_date
    row.vendor_id = ctx.vendor.vendor_id if ctx.vendor else None
    row.po_id = ctx.po.po_id if ctx.po else None
    row.po_match_type = ctx.match_type
    row.match_confidence = ctx.match_confidence
    matched = {p.inv.line_no: p.po_line.line_no for p in ctx.line_pairs}
    for line in row.lines:
        line.matched_po_line = matched.get(line.line_no)
    ctx.db.commit()


def run(ctx: RunContext) -> StageResult:
    decision = decide(ctx.findings)
    if decision == "Approve" and ctx.sibling_fraud:
        # Case 1.6: invoices that arrived in one file with a fraud warning aren't paid until Finance verifies them all.
        ctx.add("1.6", "hold", f"Another invoice in the same file has a fraud warning ({', '.join(ctx.sibling_fraud)}); "
                               "Finance must verify both.", ["Finance", "AP"], {"siblings": ctx.sibling_fraud},
                fraud=True)
        decision = decide(ctx.findings)
    if decision == "Approve" and ctx.po is not None:
        # Another run may have been approved against the same PO since stage 6 read its balance. Lock the PO,
        # read the balance again, and approve only if it still fits; save_decision's commit releases the lock.
        lock_po(ctx.db, ctx.po.po_id)
        if not s6_amounts.recheck_at_approval(ctx):
            decision = decide(ctx.findings)
    ctx.decision = decision
    why = reasons(ctx.findings, decision)
    audiences = alert_audiences(ctx.findings)
    save_decision(ctx, decision, why)
    line = headline(ctx, decision, why)
    alerts.build_and_send(ctx, decision, audiences, line)
    return StageResult(STAGE_STATUS[decision], line, {
        "decision": decision,
        "status": STATUS[decision],
        "reasons": why,
        "due_date": ctx.due_date.isoformat() if ctx.due_date else None,
        "po_id": ctx.po.po_id if ctx.po else None,
        "match_type": ctx.match_type,
        "match_confidence": ctx.match_confidence,
        "fraud": any(f.fraud for f in ctx.findings),
        "alerts": {a: [f.code for f in fs] for a, fs in audiences.items()},
        "llm_calls": ctx.llm_calls,  # for the dashboard's health strip
    })
