"""API response shapes. Money goes out as raw paise plus an en-IN display string."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, Invoice, PurchaseOrder, Review, RunFile, RunStage
from app.pipeline.context import Finding
from app.pipeline.decide import alert_audiences
from app.pipeline.runner import DECISION_ORDER
from app.services.po import invoiced_qty, po_invoiced_paise, po_total_paise
from app.utils.money import format_inr


def money(name: str, paise: int | None) -> dict:
    return {f"{name}_paise": paise, f"{name}_display": None if paise is None else format_inr(paise)}


def _iso(v) -> str | None:
    return v.isoformat() if v is not None else None


def _taxable(qty: float | None, unit_price_paise: int | None) -> int | None:
    return None if qty is None or unit_price_paise is None else round(qty * unit_price_paise)


def vendor_name(inv: Invoice) -> str | None:
    if inv.vendor is not None:
        return inv.vendor.name
    return (inv.extraction or {}).get("vendor_name")


def run_summary(inv: Invoice) -> dict:
    reasons = inv.decision_reasons or []
    return {
        "run_id": inv.run_id,
        "file_name": inv.file_name,
        "status": inv.status,
        "decision": inv.decision,
        "invoice_no": inv.invoice_no,
        "invoice_date": _iso(inv.invoice_date),
        "vendor_id": inv.vendor_id,
        "vendor_name": vendor_name(inv),
        "po_id": inv.po_id,
        "po_match_type": inv.po_match_type,
        **money("total", inv.total_paise),
        "top_reason": reasons[0]["message"] if reasons and inv.decision != "Approve" else None,
        "created_at": _iso(inv.created_at),
        "finished_at": _iso(inv.finished_at),
        "is_seed": inv.is_seed,
    }


def stage_dict(r: RunStage) -> dict:
    return {
        "order": r.stage_order,
        "name": r.stage_name,
        "status": r.status,
        "message": r.message,
        "details": r.details or {},
        "duration_ms": r.duration_ms,
        "created_at": _iso(r.created_at),
    }


def _stages(db: Session, run_id: str) -> list[RunStage]:
    return list(db.scalars(select(RunStage).where(RunStage.run_id == run_id).order_by(RunStage.stage_order)))


def findings_of(stages: list[RunStage]) -> list[dict]:
    """Every finding, tagged with the stage that raised it."""
    return [
        {**f, "stage_order": s.stage_order, "stage_name": s.stage_name}
        for s in stages for f in (s.details or {}).get("findings", [])
    ]


def alert_groups(findings: list[dict]) -> dict:
    """The same grouping the decision uses: one alert per audience; fraud removes the vendor."""
    objs = [Finding(f["code"], f["severity"], f["message"], f["audience"], {}, f.get("fraud", False)) for f in findings]
    groups = alert_audiences(objs)
    fraud = any(f.fraud for f in objs)
    return {
        "fraud": fraud,
        "vendor_suppressed": fraud and any("Vendor" in f.audience for f in objs),
        "by_audience": {
            a: [{"code": f.code, "label": f.label, "severity": f.severity, "message": f.message} for f in fs]
            for a, fs in groups.items()
        },
    }


def decision_dict(db: Session, inv: Invoice, decision_stage: RunStage | None = None) -> dict:
    if decision_stage is None:
        decision_stage = db.scalar(select(RunStage).where(
            RunStage.run_id == inv.run_id, RunStage.stage_order == DECISION_ORDER))
    details = decision_stage.details if decision_stage is not None else {}
    return {
        "run_id": inv.run_id,
        "decision": inv.decision,
        "status": inv.status,
        "headline": decision_stage.message if decision_stage is not None else None,
        "reasons": inv.decision_reasons or [],
        "fraud": details.get("fraud", False),
        "vendor_name": vendor_name(inv),
        "po_id": inv.po_id,
        **money("total", inv.total_paise),
        "due_date": _iso(inv.due_date),
    }


def po_view(db: Session, po: PurchaseOrder, run_id: str) -> dict:
    """The matched PO with balances before and after this invoice, for the comparison table."""
    total = po_total_paise(po)
    invoiced_before = po_invoiced_paise(db, po.po_id, exclude_run=run_id)
    invoiced_now = po_invoiced_paise(db, po.po_id)
    lines = []
    for ln in po.lines:
        taxable = _taxable(ln.qty, ln.unit_price_paise)
        billed = invoiced_qty(db, po.po_id, ln.line_no, exclude_run=run_id)
        lines.append({
            "line_no": ln.line_no,
            "description": ln.description,
            "hsn_code": ln.hsn_code,
            "qty": ln.qty,
            "unit": ln.unit,
            **money("unit_price", ln.unit_price_paise),
            "tax_rate": ln.tax_rate,
            **money("amount", taxable),
            **money("line_total", taxable + round(taxable * ln.tax_rate / 100)),
            "invoiced_qty_before": billed,
            "remaining_qty_before": ln.qty - billed,
        })
    previous = db.scalars(select(Invoice).where(
        Invoice.po_id == po.po_id, Invoice.run_id != run_id, Invoice.decision.is_not(None),
    ).order_by(Invoice.invoice_date, Invoice.created_at)).all()
    return {
        "po_id": po.po_id,
        "vendor_id": po.vendor_id,
        "vendor_name": po.vendor.name if po.vendor else None,
        "po_date": _iso(po.po_date),
        "status": po.status,
        "currency": po.currency,
        "payment_terms_days": po.payment_terms_days,
        "department": po.department,
        "lines": lines,
        **money("total", total),
        **money("invoiced_before", invoiced_before),
        **money("remaining_before", total - invoiced_before),  # what was left for this invoice
        **money("remaining", total - invoiced_now),  # after this invoice, if it was approved
        "previous_invoices": [
            {
                "run_id": p.run_id,
                "invoice_no": p.invoice_no,
                "invoice_date": _iso(p.invoice_date),
                "decision": p.decision,
                "counts_against_po": p.decision == "Approve",
                "is_seed": p.is_seed,
                **money("total", p.total_paise),
            }
            for p in previous
        ],
    }


def _invoice_line(ln) -> dict:
    return {
        "line_no": ln.line_no,
        "description": ln.description,
        "qty": ln.qty,
        "unit": ln.unit,
        **money("unit_price", ln.unit_price_paise),
        "tax_rate": ln.tax_rate,
        **money("amount", _taxable(ln.qty, ln.unit_price_paise)),
        "matched_po_line": ln.matched_po_line,
    }


def comparison(invoice_lines: list[dict], po: dict | None) -> list[dict]:
    """Invoice line next to the PO line it matched; unmatched PO lines at the end."""
    po_lines = {ln["line_no"]: ln for ln in (po or {}).get("lines", [])}
    rows, used = [], set()
    for il in invoice_lines:
        pl = po_lines.get(il["matched_po_line"])
        if pl is not None:
            used.add(pl["line_no"])
        rows.append({
            "invoice_line": il,
            "po_line": pl,
            "qty_diff": None if pl is None or il["qty"] is None else il["qty"] - pl["qty"],
            **money("unit_price_diff", None if pl is None or il["unit_price_paise"] is None
                    else il["unit_price_paise"] - pl["unit_price_paise"]),
        })
    rows += [{"invoice_line": None, "po_line": pl, "qty_diff": None, **money("unit_price_diff", None)}
             for n, pl in po_lines.items() if n not in used]
    return rows


def run_detail(db: Session, inv: Invoice) -> dict:
    stages = _stages(db, inv.run_id)
    findings = findings_of(stages)
    decision_stage = next((s for s in stages if s.stage_order == DECISION_ORDER), None)
    ex = inv.extraction or {}
    lines = [_invoice_line(ln) for ln in inv.lines]
    po = po_view(db, inv.po, inv.run_id) if inv.po is not None else None
    v = inv.vendor
    return {
        **run_summary(inv),
        "invoice": {
            "doc_type": inv.doc_type,
            "invoice_no": inv.invoice_no,
            "invoice_date": _iso(inv.invoice_date),
            "vendor_name_printed": ex.get("vendor_name"),
            "vendor_tax_id": inv.vendor_tax_id,
            "po_reference_printed": ex.get("po_reference"),
            "currency": ex.get("currency"),
            "bank_account": inv.bank_account,
            "ifsc": ex.get("ifsc"),
            "payment_terms_days": ex.get("payment_terms_days"),
            **money("subtotal", inv.subtotal_paise),
            **money("cgst", inv.cgst_paise),
            **money("sgst", inv.sgst_paise),
            **money("igst", inv.igst_paise),
            **money("total", inv.total_paise),
            "due_date": _iso(inv.due_date),
            "po_match_type": inv.po_match_type,
            "match_confidence": inv.match_confidence,
        },
        "vendor": None if v is None else {
            "vendor_id": v.vendor_id,
            "name": v.name,
            "tax_id": v.tax_id,
            "status": v.status,
            "msme": v.msme,
            "bank_account_on_file": v.bank_account,
            "ifsc_on_file": v.ifsc_or_swift,
            "phone": v.phone,
        },
        "extraction": inv.extraction,
        "lines": lines,
        "stages": [stage_dict(s) for s in stages],
        "findings": findings,
        "decision": decision_dict(db, inv, decision_stage) if inv.status != "running" else None,
        "alert_groups": alert_groups(findings),
        "alerts": [
            {"alert_id": a.alert_id, "audience": a.audience, "intended_for": a.intended_for, "to_email": a.to_email,
             "subject": a.subject, "status": a.status, "sent_at": _iso(a.sent_at)}
            for a in db.scalars(select(Alert).where(Alert.run_id == inv.run_id).order_by(Alert.alert_id))
        ],
        "reviews": [
            {"reviewer": r.reviewer, "action": r.action, "reason": r.reason, "field_changes": r.field_changes,
             "created_at": _iso(r.created_at)}
            for r in db.scalars(select(Review).where(Review.run_id == inv.run_id).order_by(Review.id))
        ],
        "po": po,
        "comparison": comparison(lines, po),
        "has_file": db.scalar(select(RunFile.run_id).where(RunFile.run_id == inv.run_id)) is not None,
    }
