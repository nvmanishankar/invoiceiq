"""Purchase orders: the register, Create PO and close/reopen (design doc, "Purchase orders and vendors").

POs only enter as structured data, checked here, because every invoice is matched against them.
Totals, invoiced and remaining are calculated on read, never stored.
"""

import re
from collections import defaultdict
from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import MSME_MAX_TERMS_DAYS
from app.models import CompanySettings, Invoice, InvoiceLine, PoLine, PurchaseOrder, TaxRate, Vendor, clip
from app.services.errors import Invalid
from app.services.po import APPROVED
from app.utils.gstin import state_code, state_label
from app.utils.money import format_inr, rupees_to_paise
from app.utils.timefmt import iso

# 118 stays unused: the docs use "PO118" as the example of an oddly written reference.
FIRST_NEW_PO = 119
MAX_TERMS_DAYS = 365
HSN_RE = re.compile(r"^\d{4}(\d{2}){0,2}$")  # HSN/SAC: 4, 6 or 8 digits
REOPENABLE = {"Closed": "Open", "Open": "Closed"}


class PoLineIn(BaseModel):
    description: str | None = None
    hsn_code: str | None = None
    qty: float | None = None
    unit: str | None = None
    unit_price: float | None = Field(None, description="rupees, excl. tax")
    tax_rate: float | None = None


class PoIn(BaseModel):
    vendor_id: str | None = None
    po_date: str | None = Field(None, description="YYYY-MM-DD")
    payment_terms_days: int | None = None
    department: str | None = None
    lines: list[PoLineIn] = Field(default_factory=list)


def _money(name: str, paise: int) -> dict:
    return {f"{name}_paise": paise, f"{name}_display": format_inr(paise)}


def _company(db: Session) -> CompanySettings:
    return db.scalar(select(CompanySettings).limit(1))


# --- Tax rates ------------------------------------------------------------------------------------------------------

def valid_rates(db: Session, country: str, on: date) -> list[TaxRate]:
    """Slabs in force on `on`, lowest first: the only rates a PO line may use."""
    rows = db.scalars(select(TaxRate).where(TaxRate.country == country, TaxRate.valid_from <= on)
                      .order_by(TaxRate.rate)).all()
    return [r for r in rows if r.valid_to is None or on <= r.valid_to]


def rate_dict(r: TaxRate) -> dict:
    return {"id": r.id, "country": r.country, "tax_name": r.tax_name, "rate": r.rate, "label": r.label,
            "valid_from": iso(r.valid_from), "valid_to": iso(r.valid_to)}


# --- Tax type and totals --------------------------------------------------------------------------------------------

def tax_type(company: CompanySettings, vendor: Vendor) -> str:
    """CGST+SGST in the same state, IGST across states, Import for a foreign vendor."""
    if vendor.country != company.country:
        return "Import"
    return "CGST+SGST" if state_code(vendor.tax_id or "") == company.state_code else "IGST"


def po_amounts(lines: list[PoLine], split: str) -> dict:
    """Subtotal, tax split and total, rounded per line exactly as po_total_paise does."""
    subtotal = tax = 0
    for ln in lines:
        taxable = round(ln.qty * ln.unit_price_paise)
        subtotal += taxable
        tax += round(taxable * ln.tax_rate / 100)
    if split == "Import":
        tax = 0  # IGST is paid at customs or under reverse charge, not to the vendor
    cgst = round(tax / 2) if split == "CGST+SGST" else 0
    sgst = tax - cgst if split == "CGST+SGST" else 0
    igst = tax if split == "IGST" else 0
    return {**_money("subtotal", subtotal), **_money("cgst", cgst), **_money("sgst", sgst),
            **_money("igst", igst), **_money("tax", tax), **_money("total", subtotal + tax)}


# --- Register -------------------------------------------------------------------------------------------------------

def _billed(db: Session) -> tuple[dict[str, list[Invoice]], dict[tuple[str, int], float]]:
    """Every decided invoice per PO, and approved quantities per PO line, in two queries."""
    by_po: dict[str, list[Invoice]] = defaultdict(list)
    for inv in db.scalars(select(Invoice).where(Invoice.po_id.is_not(None), Invoice.decision.is_not(None))
                          .order_by(Invoice.invoice_date, Invoice.created_at)):
        by_po[inv.po_id].append(inv)
    qty = db.execute(
        select(Invoice.po_id, InvoiceLine.matched_po_line, func.sum(InvoiceLine.qty))
        .join(Invoice, Invoice.run_id == InvoiceLine.run_id)
        .where(Invoice.decision == APPROVED, InvoiceLine.matched_po_line.is_not(None))
        .group_by(Invoice.po_id, InvoiceLine.matched_po_line)
    ).all()
    return by_po, {(po_id, line_no): float(q or 0) for po_id, line_no, q in qty}


def po_dict(po: PurchaseOrder, company: CompanySettings, invoices: list[Invoice],
            billed_qty: dict[tuple[str, int], float]) -> dict:
    vendor = po.vendor
    split = tax_type(company, vendor)
    amounts = po_amounts(po.lines, split)
    invoiced = sum(inv.total_paise or 0 for inv in invoices if inv.decision == APPROVED)
    code = state_code(vendor.tax_id or "")
    return {
        "po_id": po.po_id,
        "vendor_id": po.vendor_id,
        "vendor_name": vendor.name,
        "vendor_gstin": vendor.tax_id,
        "vendor_state": state_label(code) if vendor.country == "IN" else vendor.country,
        "vendor_msme": vendor.msme,
        "vendor_status": vendor.status,
        "po_date": iso(po.po_date),
        "currency": po.currency,
        "payment_terms_days": po.payment_terms_days,
        "department": po.department,
        "status": po.status,
        "created_by": po.created_by,
        "created_at": iso(po.created_at),
        "tax_type": split,
        **amounts,
        **_money("invoiced", invoiced),
        **_money("remaining", amounts["total_paise"] - invoiced),
        "lines": [
            {
                "line_no": ln.line_no,
                "description": ln.description,
                "hsn_code": ln.hsn_code,
                "qty": ln.qty,
                "unit": ln.unit,
                **_money("unit_price", ln.unit_price_paise),
                "tax_rate": ln.tax_rate,
                **_money("amount", round(ln.qty * ln.unit_price_paise)),
                "invoiced_qty": billed_qty.get((po.po_id, ln.line_no), 0.0),
            }
            for ln in po.lines
        ],
        "invoices": [
            {
                "run_id": inv.run_id,
                "invoice_no": inv.invoice_no,
                "invoice_date": iso(inv.invoice_date),
                "decision": inv.decision,
                "status": inv.status,
                "is_seed": inv.is_seed,
                "counts_against_po": inv.decision == APPROVED,
                "total_paise": inv.total_paise,
                "total_display": None if inv.total_paise is None else format_inr(inv.total_paise),
            }
            for inv in invoices
        ],
    }


def list_pos(db: Session) -> list[dict]:
    company = _company(db)
    by_po, billed_qty = _billed(db)
    pos = db.scalars(select(PurchaseOrder).order_by(PurchaseOrder.po_date.desc(), PurchaseOrder.po_id.desc())).all()
    return [po_dict(po, company, by_po.get(po.po_id, []), billed_qty) for po in pos]


def get_po(db: Session, po_id: str) -> dict | None:
    po = db.get(PurchaseOrder, po_id)
    if po is None:
        return None
    by_po, billed_qty = _billed(db)
    return po_dict(po, _company(db), by_po.get(po_id, []), billed_qty)


# --- Create ---------------------------------------------------------------------------------------------------------

def next_po_id(db: Session, year: int) -> str:
    """PO-2026-119, PO-2026-120, … after the highest number used this year."""
    pattern = re.compile(rf"PO-{year}-(\d+)")
    used = [int(m.group(1)) for pid in db.scalars(select(PurchaseOrder.po_id).where(
        PurchaseOrder.po_id.like(f"PO-{year}-%"))) if (m := pattern.fullmatch(pid))]
    return f"PO-{year}-{max(used + [FIRST_NEW_PO - 1]) + 1}"


def _text(v: str | None) -> str:
    return (v or "").strip()


def _rate(r: float) -> str:
    return f"{r:g}%"


def _check_lines(db: Session, body: PoIn, company: CompanySettings, po_date: date | None,
                 errors: dict[str, str]) -> list[PoLine]:
    if not body.lines:
        errors["lines"] = "Add at least one line item."
        return []
    allowed = {r.rate for r in valid_rates(db, company.country, po_date)} if po_date else set()
    out = []
    for i, ln in enumerate(body.lines):
        n = i + 1
        key = f"lines.{i}"
        desc, hsn, unit = _text(ln.description), _text(ln.hsn_code), _text(ln.unit)
        if not desc:
            errors[f"{key}.description"] = f"Line {n}: describe the item."
        if hsn and not HSN_RE.match(hsn):
            errors[f"{key}.hsn_code"] = f"Line {n}: an HSN/SAC code is 4, 6 or 8 digits (or leave it blank)."
        if ln.qty is None or ln.qty <= 0:
            errors[f"{key}.qty"] = f"Line {n}: quantity must be more than 0."
        if not unit:
            errors[f"{key}.unit"] = f"Line {n}: choose a unit."
        price = rupees_to_paise(ln.unit_price) if ln.unit_price is not None else None
        if price is None or price <= 0:
            errors[f"{key}.unit_price"] = f"Line {n}: unit price must be more than ₹0."
        if ln.tax_rate is None:
            errors[f"{key}.tax_rate"] = f"Line {n}: choose a tax rate."
        elif po_date and ln.tax_rate not in allowed:
            slabs = ", ".join(_rate(r) for r in sorted(allowed)) or "none"
            errors[f"{key}.tax_rate"] = (f"Line {n}: {_rate(ln.tax_rate)} isn't a valid GST rate on "
                                         f"{po_date:%d %b %Y}. Valid rates then: {slabs}.")
        out.append(PoLine(line_no=n, description=desc, hsn_code=hsn or None, qty=ln.qty or 0,
                          unit=clip(PoLine, "unit", unit), unit_price_paise=price or 0, tax_rate=ln.tax_rate or 0))
    return out


def create_po(db: Session, body: PoIn, role: str, today: date) -> tuple[PurchaseOrder, list[str]]:
    """Validate every field, then save. Returns the PO and any warnings (e.g. MSME terms)."""
    company = _company(db)
    errors: dict[str, str] = {}
    warnings: list[str] = []

    vendor = db.get(Vendor, _text(body.vendor_id)) if _text(body.vendor_id) else None
    if not _text(body.vendor_id):
        errors["vendor_id"] = "Choose a vendor."
    elif vendor is None:
        errors["vendor_id"] = f"There's no vendor {body.vendor_id}."
    elif vendor.status != "Active":
        errors["vendor_id"] = f"{vendor.name} is {vendor.status.lower()}, so no new POs can be raised for them."

    po_date = None
    try:
        po_date = date.fromisoformat(_text(body.po_date)) if _text(body.po_date) else None
    except ValueError:
        pass
    if po_date is None:
        errors["po_date"] = "Enter the PO date as YYYY-MM-DD."
    elif po_date > today:
        errors["po_date"] = f"The PO date can't be in the future (today is {today:%d %b %Y})."

    terms = body.payment_terms_days
    if terms is None or not 0 <= terms <= MAX_TERMS_DAYS:
        errors["payment_terms_days"] = f"Payment terms are a whole number of days from 0 to {MAX_TERMS_DAYS}."
    elif vendor is not None and vendor.msme and terms > MSME_MAX_TERMS_DAYS:
        warnings.append(f"{vendor.name} is an MSME: the law caps payment at {MSME_MAX_TERMS_DAYS} days, so invoices "
                        f"will fall due after {MSME_MAX_TERMS_DAYS} days, not {terms}.")

    lines = _check_lines(db, body, company, po_date if "po_date" not in errors else None, errors)
    if errors:
        raise Invalid(errors)

    for _ in range(3):  # two people saving at once: the loser takes the next number
        po = PurchaseOrder(po_id=next_po_id(db, today.year), vendor_id=vendor.vendor_id, po_date=po_date,
                           currency=vendor.currency or company.currency, payment_terms_days=terms,
                           department=clip(PurchaseOrder, "department", _text(body.department)) or None,
                           status="Open", created_by=role)
        po.lines = lines
        db.add(po)
        try:
            db.commit()
            return po, warnings
        except IntegrityError:
            db.rollback()
            lines = [PoLine(**{c: getattr(ln, c) for c in ("line_no", "description", "hsn_code", "qty", "unit",
                                                          "unit_price_paise", "tax_rate")}) for ln in lines]
    raise Invalid({"po_id": "Couldn't assign a PO number. Please try again."}, status=409)


def set_po_status(db: Session, po_id: str, status: str) -> PurchaseOrder:
    po = db.get(PurchaseOrder, po_id)
    if po is None:
        raise Invalid({"po_id": f"PO {po_id} not found."}, status=404)
    if status not in REOPENABLE:
        raise Invalid({"status": "A PO can be set to Open or Closed."})
    if po.status not in REOPENABLE:
        raise Invalid({"status": f"{po.po_id} is {po.status.lower()} and can't be changed."}, status=409)
    po.status = status
    db.commit()
    return po
