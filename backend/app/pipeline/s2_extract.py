"""Stage 2: extract fields with one LLM call (cases 1.4-1.7, 2.1-2.3)."""

from datetime import date

from app import llm
from app.models import Invoice, InvoiceLine, clip
from app.pipeline.context import RunContext, StageResult
from app.schemas import ExtractedInvoice
from app.utils.money import format_inr, rupees_to_paise
from app.utils.normalise import norm_full, normalise_currency

FIELD_LABELS = {
    "invoice_number": "invoice number",
    "invoice_date": "invoice date",
    "total": "total",
    "vendor_gstin": "vendor GSTIN",
    "bank_account": "bank account",
    "po_reference": "PO reference",
}


def _paise(v: float | None) -> int | None:
    return None if v is None else rupees_to_paise(v)


def _iso_date(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None  # left null; stage 3 reports the missing date


def back_calculate_tax(ctx: RunContext, inv: ExtractedInvoice) -> None:
    """Case 2.3: prices include GST, so strip tax from each line at its printed rate."""
    changed = []
    for line in inv.lines:
        if not line.tax_rate:
            continue
        factor = 1 + line.tax_rate / 100
        before = {"unit_price": line.unit_price, "amount": line.amount}
        if line.unit_price is not None:
            line.unit_price = round(line.unit_price / factor, 2)
        if line.amount is not None:
            line.amount = round(line.amount / factor, 2)
        changed.append({"description": line.description, "rate": line.tax_rate, "before": before,
                        "after": {"unit_price": line.unit_price, "amount": line.amount}})
    if inv.subtotal is None or inv.subtotal == inv.total:
        amounts = [line.amount for line in inv.lines]
        inv.subtotal = round(sum(amounts), 2) if amounts and None not in amounts else None
    inv.tax_inclusive = False
    ctx.add("2.3", "info", "Prices on this invoice include GST, so the tax was separated from each line before checking.",
            [], {"lines": changed})


def save_invoice_fields(ctx: RunContext, inv: ExtractedInvoice) -> None:
    row = ctx.db.get(Invoice, ctx.run_id)
    if row is None:
        return
    write_invoice_row(row, ctx.doc_type, ctx.extraction, inv)
    ctx.db.commit()


def write_invoice_row(row: Invoice, doc_type: str | None, extraction: dict | None, inv: ExtractedInvoice) -> None:
    """The extracted fields as invoice columns and lines. Strings are cut to fit their columns."""
    row.doc_type = clip(Invoice, "doc_type", doc_type)
    row.invoice_no = clip(Invoice, "invoice_no", inv.invoice_number)
    row.invoice_no_norm = clip(Invoice, "invoice_no_norm", norm_full(inv.invoice_number) or None)
    row.invoice_date = _iso_date(inv.invoice_date)
    row.vendor_tax_id = clip(Invoice, "vendor_tax_id", inv.vendor_gstin)
    row.subtotal_paise = _paise(inv.subtotal)
    row.cgst_paise = _paise(inv.cgst)
    row.sgst_paise = _paise(inv.sgst)
    row.igst_paise = _paise(inv.igst)
    row.total_paise = _paise(inv.total)
    row.bank_account = clip(Invoice, "bank_account", inv.bank_account)
    row.extraction = extraction
    row.lines = [
        InvoiceLine(line_no=i, description=line.description, qty=line.qty, unit=clip(InvoiceLine, "unit", line.unit),
                    unit_price_paise=_paise(line.unit_price), tax_rate=line.tax_rate)
        for i, line in enumerate(inv.lines, start=1)
    ]


def run(ctx: RunContext) -> StageResult:
    ex = llm.extract(ctx.file_bytes, ctx.file_hash, ctx.text, source=ctx.file_name, ctx=ctx)
    if ex is None:
        ctx.halt = True
        ctx.add("2.2", "hold", "The invoice couldn't be read automatically. A person needs to enter the details.", ["AP"],
                {"reason": "extraction unavailable"})
        return StageResult("fail", "Couldn't read automatically; sent to review", {"llm_calls": ctx.llm_calls})

    ctx.doc_type = ex.doc_type
    if ex.doc_type != "invoice":
        label = ex.doc_type.replace("_", " ")
        if ex.doc_type == "credit_note":
            ctx.add("1.5", "hold", "This document is a credit note, not an invoice. Route it to credit note handling; don't pay it.",
                    ["AP"], {"doc_type": ex.doc_type})
        else:
            ctx.add("1.4", "reject", f"This document is a {label}, not an invoice.", ["Vendor"], {"doc_type": ex.doc_type})
        ctx.halt = True
        ctx.extraction = ex.invoices[0].model_dump(mode="json") if ex.invoices else None
        return StageResult("fail", f"Not an invoice: {label}", {"doc_type": ex.doc_type, "fields": ctx.extraction})

    if not ex.invoices:
        ctx.halt = True
        ctx.add("2.2", "hold", "No invoice details could be read from this file. A person needs to enter them.", ["AP"])
        return StageResult("fail", "No invoice details found; sent to review", {})

    if len(ex.invoices) > 1:
        ctx.halt = True
        pages = [i.page_range for i in ex.invoices]
        if not ex.boundaries_clear:
            ctx.add("1.7", "hold", "This file seems to contain several invoices. Please send each as a separate PDF.",
                    ["Vendor"], {"count": len(ex.invoices), "page_ranges": pages})
            return StageResult("warn", "Several invoices, unclear boundaries", {"count": len(ex.invoices)})
        # Splitting into child runs is a stretch goal; until then a person splits the file.
        ctx.add("1.6", "hold", f"This file contains {len(ex.invoices)} separate invoices. Each needs its own run.",
                ["AP"], {"count": len(ex.invoices), "page_ranges": pages})
        return StageResult("info", f"{len(ex.invoices)} invoices in one file", {"count": len(ex.invoices), "page_ranges": pages})

    inv = ex.invoices[0]
    inv.currency = normalise_currency(inv.currency)  # 'Rs.', '₹', 'INR' → 'INR'
    if inv.tax_inclusive:
        back_calculate_tax(ctx, inv)
    low = [FIELD_LABELS[f] for f, c in inv.confidence.model_dump().items() if c == "low"]
    if low:
        ctx.add("2.2", "hold", f"Couldn't read the {', '.join(low)} reliably; please confirm.", ["AP"], {"fields": low})
    ctx.extraction = inv.model_dump(mode="json")
    save_invoice_fields(ctx, inv)

    msg = f"{len(inv.lines)} line(s), total {format_inr(_paise(inv.total))}"
    if low:
        msg += f"; low confidence: {', '.join(low)}"
    return StageResult("warn" if low else "pass", msg, {"fields": ctx.extraction, "llm_calls": ctx.llm_calls})
