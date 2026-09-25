"""Stage 6: amounts and quantities against the matched PO (cases 6.1-6.9)."""

from sqlalchemy import select

from app.models import Invoice, PurchaseOrder
from app.pipeline.context import RunContext, StageResult, summarise
from app.services.po import APPROVED, invoiced_qty, po_remaining_paise, po_total_paise
from app.utils.money import allowed_diff, format_inr, format_qty


def ledger_rows(ctx: RunContext, po: PurchaseOrder) -> list[dict]:
    rows = ctx.db.scalars(select(Invoice).where(Invoice.po_id == po.po_id, Invoice.decision == APPROVED,
                                                Invoice.run_id != ctx.run_id).order_by(Invoice.invoice_date))
    return [{"run_id": r.run_id, "invoice_no": r.invoice_no,
             "invoice_date": r.invoice_date.isoformat() if r.invoice_date else None, "total_paise": r.total_paise}
            for r in rows]


def add_over_balance(ctx: RunContext, po: PurchaseOrder, remaining: int, total: int, details: dict,
                     note: str = "") -> None:
    ctx.add("6.5", "hold", f"Only {format_inr(remaining)} remains on {po.po_id}; this invoice is "
                           f"{format_inr(total)}.{note}", ["Vendor"], details)


def add_over_quantity(ctx: RunContext, po: PurchaseOrder, il, pl, already: float, check: dict,
                      note: str = "") -> None:
    ctx.add("6.6", "hold", f"{il.description}: {format_qty(already + il.qty)} invoiced in total "
                           f"vs {format_qty(pl.qty)} ordered on {po.po_id}.{note}", ["Vendor"], check)


def _tolerance(ctx: RunContext, expected: int) -> int:
    return allowed_diff(expected, ctx.company.tolerance_pct, ctx.company.tolerance_abs_paise)


APPROVED_MEANWHILE = " Another invoice against it was approved while this one was being checked."


def recheck_at_approval(ctx: RunContext) -> bool:
    """The balance and quantity rules again, just before approving, on the ledger as it is now. The caller holds the
    PO lock (services/po.lock_po), so nothing can be approved against the PO between this read and the approval.
    Adds 6.5 / 6.6 Holds and returns False when the invoice no longer fits."""
    po, inv = ctx.po, ctx.inv
    before = len(ctx.findings)
    remaining = po_remaining_paise(ctx.db, po, exclude_run=ctx.run_id)
    total = inv.total_paise
    if total is not None and total > remaining + _tolerance(ctx, remaining):
        add_over_balance(ctx, po, remaining, total, {
            "po_id": po.po_id, "po_total_paise": po_total_paise(po), "remaining_paise": remaining,
            "invoice_total_paise": total, "previous_invoices": ledger_rows(ctx, po), "at_approval": True,
        }, APPROVED_MEANWHILE)
    if not ctx.bundled:
        for pair in ctx.line_pairs:
            il, pl = pair.inv, pair.po_line
            if il.qty is None:
                continue
            already = invoiced_qty(ctx.db, po.po_id, pl.line_no, exclude_run=ctx.run_id)
            if already + il.qty > pl.qty + 1e-9:
                add_over_quantity(ctx, po, il, pl, already, {
                    "invoice_line": il.description, "po_line": pl.description, "po_line_no": pl.line_no,
                    "already": already, "this_invoice": il.qty, "ordered": pl.qty, "at_approval": True,
                }, APPROVED_MEANWHILE)
    return len(ctx.findings) == before


def run(ctx: RunContext) -> StageResult:
    po = ctx.po
    if po is None:
        return StageResult("info", "Skipped: no PO matched", {})
    inv = ctx.inv

    def tol(expected: int) -> int:
        return _tolerance(ctx, expected)

    before = len(ctx.findings)

    po_total = po_total_paise(po)
    remaining = po_remaining_paise(ctx.db, po, exclude_run=ctx.run_id)
    previous = ledger_rows(ctx, po)
    details = {"po_id": po.po_id, "po_total_paise": po_total, "remaining_paise": remaining,
               "invoice_total_paise": inv.total_paise, "previous_invoices": previous}

    # Total against the remaining balance.
    total = inv.total_paise
    if total is not None:
        if total > remaining + tol(remaining):
            if previous:
                add_over_balance(ctx, po, remaining, total, details)
            else:
                ctx.add("6.3", "hold", f"This invoice ({format_inr(total)}) is more than {po.po_id} allows "
                                       f"({format_inr(remaining)}), beyond the tolerance of {format_inr(tol(remaining))}.",
                        ["Vendor", "AP"], details)
        elif previous:
            ctx.add("6.4", "pass", f"Part-billing: {format_inr(total)} fits the {format_inr(remaining)} remaining on "
                                   f"{po.po_id}.", [], details)
        elif total == po_total:
            ctx.add("6.1", "pass", f"The total matches {po.po_id} exactly.", [], details)
        elif abs(total - po_total) <= tol(po_total):
            ctx.add("6.2", "pass", f"The total differs from {po.po_id} by {format_inr(abs(total - po_total))}, "
                                   "within tolerance.", [], details)
        else:
            ctx.add("6.9", "pass", f"Partial billing: {format_inr(po_total - total)} stays open on {po.po_id}.",
                    [], details)

    # Lines against the PO lines they were paired with in stage 5.
    line_checks = []
    if ctx.bundled:
        details["lines"] = "Not itemised; checked at total level only"
    else:
        for pair in ctx.line_pairs:
            il, pl = pair.inv, pair.po_line
            check = {"invoice_line": il.description, "po_line": pl.description, "po_line_no": pl.line_no}
            if il.qty is not None:
                already = invoiced_qty(ctx.db, po.po_id, pl.line_no, exclude_run=ctx.run_id)
                check.update(already=already, this_invoice=il.qty, ordered=pl.qty)
                if already + il.qty > pl.qty + 1e-9:
                    add_over_quantity(ctx, po, il, pl, already, check)
            if il.unit_price_paise is not None:
                check.update(invoice_price_paise=il.unit_price_paise, po_price_paise=pl.unit_price_paise)
                if il.unit_price_paise > pl.unit_price_paise + tol(pl.unit_price_paise):
                    ctx.add("6.7", "hold", f"{il.description}: {format_inr(il.unit_price_paise)} per unit vs "
                                           f"{format_inr(pl.unit_price_paise)} on {po.po_id}.", ["Vendor"], check)
            line_checks.append(check)
        for il in ctx.unpaired_lines:
            ctx.add("6.8", "hold", f"'{il.description}' isn't on {po.po_id}.", ["Vendor", "Procurement"],
                    {"invoice_line": il.description})
        details["lines"] = line_checks

    holds = [f for f in ctx.findings[before:] if f.severity == "hold"]
    if holds:
        return StageResult("warn", summarise(holds), details)
    return StageResult("pass", f"Within {po.po_id}: {format_inr(total)} of {format_inr(remaining)} remaining", details)
