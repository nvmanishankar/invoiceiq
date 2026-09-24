"""Stage 3: completeness and maths (cases 3.1-3.7)."""

from app.config import MATHS_TOLERANCE_PAISE
from app.pipeline.context import RunContext, StageResult, summarise
from app.utils.money import format_inr
from app.utils.normalise import normalise_currency


def run(ctx: RunContext) -> StageResult:
    inv = ctx.inv
    before = len(ctx.findings)

    if not inv.invoice_no:
        ctx.add("3.1", "hold", "The invoice has no invoice number.", ["Vendor"])
    if inv.invoice_date is None:
        if inv.invoice_date_raw:
            ctx.add("3.2", "hold", f"The invoice date '{inv.invoice_date_raw}' couldn't be read as a date.", ["Vendor"],
                    {"printed": inv.invoice_date_raw})
        else:
            ctx.add("3.2", "hold", "The invoice has no invoice date.", ["Vendor"])
    if inv.total_paise is None:
        ctx.add("3.3", "hold", "The invoice has no total amount.", ["Vendor"])

    # 3.4: only when every line can be valued; a partial sum would invent a gap.
    line_values = [ln.taxable_paise for ln in inv.lines]
    lines_sum = sum(line_values) if line_values and None not in line_values else None
    if lines_sum is not None and inv.subtotal_paise is not None and abs(lines_sum - inv.subtotal_paise) > MATHS_TOLERANCE_PAISE:
        gap = abs(lines_sum - inv.subtotal_paise)
        ctx.add("3.4", "hold",
                f"Line items add up to {format_inr(lines_sum)} but the subtotal says {format_inr(inv.subtotal_paise)} "
                f"(gap {format_inr(gap)}).", ["Vendor"], {"lines_sum_paise": lines_sum, "subtotal_paise": inv.subtotal_paise})

    tax = inv.tax_paise
    if inv.subtotal_paise is not None and inv.total_paise is not None \
            and abs(inv.subtotal_paise + tax - inv.total_paise) > MATHS_TOLERANCE_PAISE:
        ctx.add("3.5", "hold",
                f"Subtotal {format_inr(inv.subtotal_paise)} + tax {format_inr(tax)} doesn't equal the total "
                f"{format_inr(inv.total_paise)}.", ["Vendor"])

    if inv.invoice_date and inv.invoice_date > ctx.today:
        ctx.add("3.6", "hold", f"The invoice is dated {inv.invoice_date:%d %b %Y}, which is in the future.", ["Vendor"])

    ctx.bundled = not inv.lines or (len(inv.lines) == 1 and inv.lines[0].qty is None)
    if ctx.bundled:
        ctx.add("3.7", "info", "The invoice has no itemised quantities, so it's checked at total level only.", [])

    currency = normalise_currency(inv.currency)
    new = ctx.findings[before:]
    holds = [f for f in new if f.severity == "hold"]
    details = {"lines_sum_paise": lines_sum, "subtotal_paise": inv.subtotal_paise, "tax_paise": tax,
               "total_paise": inv.total_paise, "currency": currency, "bundled": ctx.bundled}
    if holds:
        return StageResult("warn", summarise(holds), details)
    return StageResult("pass", f"All required fields present; arithmetic adds up ({format_inr(inv.total_paise)})", details)
