"""India GST: split by state, rate valid on the date, rate matches the PO, amount right (cases 8.1-8.7)."""

from datetime import date

from sqlalchemy import select

from app.config import MATHS_TOLERANCE_PAISE
from app.models import TaxRate
from app.pipeline.context import RunContext, StageResult, summarise
from app.utils.gstin import state_code, state_label
from app.utils.money import format_inr

SPLIT_LABEL = {"CGST+SGST": "CGST + SGST", "IGST": "IGST", "None": "no GST", "Mixed": "both CGST + SGST and IGST"}


def _rate(r: float) -> str:
    return f"{r:g}%"


def rate_valid_on(db, rate: float, on: date) -> bool:
    rows = db.scalars(select(TaxRate).where(TaxRate.country == "IN", TaxRate.rate == rate))
    return any(r.valid_from <= on and (r.valid_to is None or on <= r.valid_to) for r in rows)


def actual_split(cgst: int | None, sgst: int | None, igst: int | None) -> str:
    local, inter = bool(cgst or sgst), bool(igst)
    return "Mixed" if local and inter else "CGST+SGST" if local else "IGST" if inter else "None"


class IndiaGST:
    name = "India GST"

    def check(self, ctx: RunContext) -> StageResult:
        inv, vendor, company = ctx.inv, ctx.vendor, ctx.company
        before = len(ctx.findings)
        tax = inv.tax_paise

        if vendor.country != company.country:
            details = {"import": True, "tax_paise": tax}
            if tax > 0:
                ctx.add("8.7", "hold", f"{vendor.name} is outside India and shouldn't charge GST; Indian tax is paid "
                                       "via customs or reverse charge.", ["Vendor"], details)
                return StageResult("warn", "Foreign vendor charged GST", details)
            ctx.add("8.7", "info", "Import: no GST on the invoice, as expected. IGST is payable separately "
                                   "(customs or reverse charge).", [], details)
            return StageResult("info", "Import: no GST expected", details)

        vendor_state = state_code(vendor.tax_id or "")
        same_state = vendor_state == company.state_code
        rates = [ln.tax_rate for ln in inv.lines if ln.tax_rate is not None]
        nil = bool(rates) and all(r == 0 for r in rates)
        expected = "None" if nil else "CGST+SGST" if same_state else "IGST"
        actual = actual_split(inv.cgst_paise, inv.sgst_paise, inv.igst_paise)
        details = {"vendor_state": vendor_state, "company_state": company.state_code, "expected_split": expected,
                   "actual_split": actual, "tax_paise": tax, "rates": sorted(set(rates))}

        if actual != expected:
            ctx.add("8.3", "hold", f"{vendor.name} is in {state_label(vendor_state)} and we are in "
                                   f"{state_label(company.state_code)}: {SPLIT_LABEL[expected]} applies, but the invoice "
                                   f"charges {SPLIT_LABEL[actual]}. Please reissue the invoice.", ["Vendor"], details)

        paired = {id(p.inv): p for p in ctx.line_pairs}
        for ln in inv.lines:
            if ln.tax_rate is None:
                continue
            pair = paired.get(id(ln))
            if inv.invoice_date is not None and not rate_valid_on(ctx.db, ln.tax_rate, inv.invoice_date):
                ctx.add("8.5", "hold", f"{ln.description}: {_rate(ln.tax_rate)} isn't a valid GST rate on "
                                       f"{inv.invoice_date:%d %b %Y} (12% and 28% ended on 21 Sep 2025).", ["Vendor"],
                        {"line": ln.description, "rate": ln.tax_rate})
            elif pair is not None and ln.tax_rate != pair.po_line.tax_rate:
                ctx.add("8.4", "hold", f"{ln.description}: {_rate(ln.tax_rate)} on the invoice vs "
                                       f"{_rate(pair.po_line.tax_rate)} on {ctx.po.po_id}.", ["Vendor"],
                        {"line": ln.description, "invoice_rate": ln.tax_rate, "po_rate": pair.po_line.tax_rate})
        if inv.invoice_date is None:
            details["rate_validity"] = "Not checked: no invoice date"

        # 8.6 only when every line has a value and a rate; otherwise the expected tax would be a guess.
        parts = [(ln.taxable_paise, ln.tax_rate) for ln in inv.lines]
        if parts and all(v is not None and r is not None for v, r in parts):
            expected_tax = round(sum(v * r / 100 for v, r in parts))
            details["expected_tax_paise"] = expected_tax
            if abs(expected_tax - tax) > MATHS_TOLERANCE_PAISE:
                ctx.add("8.6", "hold", f"Tax should be {format_inr(expected_tax)} at the line rates, but the invoice "
                                       f"shows {format_inr(tax)}.", ["Vendor"], details)
        if actual == "CGST+SGST" and abs((inv.cgst_paise or 0) - (inv.sgst_paise or 0)) > MATHS_TOLERANCE_PAISE:
            ctx.add("8.6", "hold", f"CGST ({format_inr(inv.cgst_paise)}) and SGST ({format_inr(inv.sgst_paise)}) "
                                   "should be equal halves.", ["Vendor"], details)

        holds = [f for f in ctx.findings[before:] if f.severity == "hold"]
        if holds:
            return StageResult("warn", summarise(holds), details)
        rate_text = "/".join(sorted({_rate(r) for r in rates})) or "the stated rate"
        if expected == "CGST+SGST":
            half = "/".join(sorted({_rate(r / 2) for r in rates})) or "half"
            ctx.add("8.1", "pass", f"Same state: CGST {half} + SGST {half} verified ({format_inr(tax)}).", [], details)
        elif expected == "IGST":
            ctx.add("8.2", "pass", f"Different states: IGST {rate_text} verified ({format_inr(tax)}).", [], details)
        return StageResult("pass", f"{SPLIT_LABEL[expected]} verified, {format_inr(tax)}", details)
