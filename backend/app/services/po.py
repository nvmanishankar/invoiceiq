"""PO values calculated on read, never stored (build guide section 5)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Invoice, InvoiceLine, PurchaseOrder

APPROVED = "Approve"


def po_total_paise(po: PurchaseOrder) -> int:
    """Sum over lines of qty * unit_price plus tax at the line rate."""
    total = 0
    for line in po.lines:
        taxable = round(line.qty * line.unit_price_paise)
        total += taxable + round(taxable * line.tax_rate / 100)
    return total


def po_invoiced_paise(db: Session, po_id: str, exclude_run: str | None = None) -> int:
    q = select(func.coalesce(func.sum(Invoice.total_paise), 0)).where(
        Invoice.po_id == po_id, Invoice.decision == APPROVED
    )
    if exclude_run:
        q = q.where(Invoice.run_id != exclude_run)
    return int(db.scalar(q))


def po_remaining_paise(db: Session, po: PurchaseOrder, exclude_run: str | None = None) -> int:
    return po_total_paise(po) - po_invoiced_paise(db, po.po_id, exclude_run)


def invoiced_qty(db: Session, po_id: str, line_no: int, exclude_run: str | None = None) -> float:
    q = (
        select(func.coalesce(func.sum(InvoiceLine.qty), 0))
        .join(Invoice, Invoice.run_id == InvoiceLine.run_id)
        .where(Invoice.po_id == po_id, Invoice.decision == APPROVED, InvoiceLine.matched_po_line == line_no)
    )
    if exclude_run:
        q = q.where(Invoice.run_id != exclude_run)
    return float(db.scalar(q))
