"""PO values calculated on read, never stored (build guide section 5)."""

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Invoice, InvoiceLine, PurchaseOrder
from app.utils.money import format_inr, format_qty

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


def lock_po(db: Session, po_id: str) -> None:
    """Lock the PO for the rest of this transaction, so a balance read now can't be overtaken before the approval
    commits. Postgres: SELECT ... FOR UPDATE on the PO row. SQLite locks the whole database for writing instead
    (BEGIN IMMEDIATE); it can only start a transaction, so whatever is pending is committed first.
    The caller's next commit (or rollback) releases the lock."""
    if db.get_bind().dialect.name == "sqlite":
        db.commit()
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    else:
        db.execute(select(PurchaseOrder.po_id).where(PurchaseOrder.po_id == po_id).with_for_update())


def unit_label(unit: str | None, qty: float) -> str:
    """'ream' → 'reams' for more than one; short codes (pcs, kg, nos) as they are."""
    u = (unit or "").strip()
    if not u:
        return ""
    if qty != 1 and u.isalpha() and len(u) >= 4 and not u.lower().endswith("s"):
        u += "s"
    return f" {u}"


@dataclass
class Overage:
    """How far approving one invoice would take its PO past what's left on it."""

    po_id: str
    amount_paise: int = 0  # over the remaining balance; 0 when it fits
    lines: list[dict] = field(default_factory=list)  # PO lines whose ordered quantity would be passed

    def __bool__(self) -> bool:
        return self.amount_paise > 0 or bool(self.lines)

    @property
    def text(self) -> str:
        """'₹23,600 and 100 reams'."""
        parts = [format_inr(self.amount_paise)] if self.amount_paise > 0 else []
        parts += [f"{format_qty(ln['over_qty'])}{unit_label(ln['unit'], ln['over_qty'])}" for ln in self.lines]
        return " and ".join([", ".join(parts[:-1]), parts[-1]] if len(parts) > 2 else parts)

    def as_dict(self) -> dict:
        return {"po_id": self.po_id, "amount_paise": self.amount_paise,
                "amount_display": format_inr(self.amount_paise) if self.amount_paise > 0 else None,
                "lines": self.lines, "text": self.text}


def overage(db: Session, row: Invoice) -> Overage | None:
    """What approving this run would take its PO over, on the balances as they are now; None without a PO.
    Exact, no tolerance: a person approving past the PO sees every rupee and unit of it."""
    po = row.po
    if po is None:
        return None
    out = Overage(po.po_id)
    if row.total_paise is not None:
        out.amount_paise = max(0, row.total_paise - po_remaining_paise(db, po, exclude_run=row.run_id))
    this_invoice: dict[int, float] = {}
    for ln in row.lines:
        if ln.matched_po_line is not None and ln.qty is not None:
            this_invoice[ln.matched_po_line] = this_invoice.get(ln.matched_po_line, 0) + ln.qty
    for pl in po.lines:
        if pl.line_no not in this_invoice:
            continue
        total_qty = invoiced_qty(db, po.po_id, pl.line_no, exclude_run=row.run_id) + this_invoice[pl.line_no]
        if total_qty > pl.qty + 1e-9:
            out.lines.append({"po_line_no": pl.line_no, "description": pl.description, "unit": pl.unit,
                              "ordered": pl.qty, "invoiced_with_this": total_qty, "over_qty": total_qty - pl.qty})
    return out
