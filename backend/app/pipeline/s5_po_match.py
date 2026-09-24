"""Stage 5: match the PO. Explicit reference, else filters then scoring (cases 5.1-5.10)."""

from sqlalchemy import select

from app import config
from app.models import PurchaseOrder
from app.pipeline.context import RunContext, StageResult
from app.services.matching import (
    SOURCE_TEXT,
    PoScore,
    needed_pairs,
    pair_lines,
    score_po,
    similarity_table,
)
from app.services.po import po_remaining_paise
from app.utils.money import allowed_diff, format_inr, format_qty
from app.utils.normalise import po_candidates_from_ref

LOWER = {"High": "Medium", "Medium": "Low", "Low": "Low"}


def _lines_text(lines) -> str:
    """'25 × Standard office chair at ₹4,000' for PO lines or invoice lines."""
    parts = []
    for ln in lines:
        price = getattr(ln, "unit_price_paise", None)
        parts.append(f"{format_qty(ln.qty)} × {ln.description}" + (f" at {format_inr(price)}" if price is not None else ""))
    return "; ".join(parts)


def _set_pairs(ctx: RunContext, po: PurchaseOrder, sims) -> None:
    ctx.line_pairs, ctx.unpaired_lines = pair_lines(ctx.inv.lines, po, sims)


def _explicit(ctx: RunContext, raw_ref: str, year: int) -> StageResult | None:
    """Look up the printed reference. Returns None if it names no PO we have."""
    tried = po_candidates_from_ref(raw_ref, year)
    po = next((p for p in (ctx.db.get(PurchaseOrder, pid) for pid in tried) if p is not None), None)
    if po is None:
        return None
    vendor, inv_date = ctx.vendor, ctx.inv.invoice_date
    details = {"printed": raw_ref, "tried": tried, "po_id": po.po_id}
    if vendor is not None and po.vendor_id != vendor.vendor_id:
        ctx.add("5.5", "hold", f"{po.po_id} was issued to {po.vendor.name}, not {vendor.name}.", ["Vendor"], details)
        return StageResult("warn", f"{po.po_id} belongs to another vendor", details)

    exact = raw_ref.strip().upper() == po.po_id
    if exact:
        ctx.add("5.1", "pass", f"Matched {po.po_id} from the reference printed on the invoice.", [], details)
    else:
        ctx.add("5.2", "pass", f"The reference '{raw_ref}' was read as {po.po_id}.", [], details)
    if po.status != "Open":
        ctx.add("5.4", "hold", f"{po.po_id} is {po.status.lower()}, so no more invoices can be paid against it.",
                ["Procurement"], details)
    elif inv_date and inv_date < po.po_date:
        ctx.add("5.6", "hold", f"The invoice is dated {inv_date:%d %b %Y}, before {po.po_id} was raised "
                               f"on {po.po_date:%d %b %Y}.", ["Procurement", "AP"], details)
    ctx.po, ctx.match_type, ctx.match_confidence = po, "Explicit", "High"
    sims = similarity_table(ctx, needed_pairs(ctx.inv.lines, [po], skip_exact=True))
    _set_pairs(ctx, po, sims)
    details["similarity_source"] = sims.source
    how = "explicit" if exact else f"explicit, printed as '{raw_ref}'"
    return StageResult("pass", f"Matched {po.po_id} ({how})", details)


def _filter(ctx: RunContext) -> tuple[list[PurchaseOrder], list[dict], dict[str, int]]:
    """Hard filters: same vendor, open, enough balance, PO not after the invoice."""
    inv, vendor = ctx.inv, ctx.vendor
    survivors, log, remaining = [], [], {}
    for po in ctx.db.scalars(select(PurchaseOrder).order_by(PurchaseOrder.po_id)):
        if po.vendor_id != vendor.vendor_id:
            log.append({"po_id": po.po_id, "eliminated_by": "Vendor", "reason": po.vendor.name})
            continue
        if po.status != "Open":
            log.append({"po_id": po.po_id, "eliminated_by": "Status", "reason": po.status})
            continue
        rem = po_remaining_paise(ctx.db, po, exclude_run=ctx.run_id)
        remaining[po.po_id] = rem
        tol = allowed_diff(rem, ctx.company.tolerance_pct, ctx.company.tolerance_abs_paise)
        if inv.total_paise is not None and inv.total_paise > rem + tol:
            log.append({"po_id": po.po_id, "eliminated_by": "Balance", "reason": f"Only {format_inr(rem)} remains"})
            continue
        if inv.invoice_date is not None and inv.invoice_date < po.po_date:
            log.append({"po_id": po.po_id, "eliminated_by": "Date",
                        "reason": f"Raised {po.po_date:%d %b %Y}, after the invoice"})
            continue
        log.append({"po_id": po.po_id, "eliminated_by": None, "reason": "Survives"})
        survivors.append(po)
    return survivors, log, remaining


def _spans_two_pos(ctx: RunContext, survivors, sims) -> bool:
    """5.10: no single PO covers every line, but together they do."""
    lines = ctx.inv.lines
    if len(lines) < 2 or len(survivors) < 2:
        return False
    covers = {po.po_id: {il.line_no for il in lines
                         if any(sims.get(il.description, pl.description) >= config.PO_DESC_MIN_SIM for pl in po.lines)}
              for po in survivors}
    every = {il.line_no for il in lines}
    return not any(c == every for c in covers.values()) and set().union(*covers.values()) == every


def _key_sentence(ctx: RunContext, winner: PurchaseOrder, win: PoScore, runner: PurchaseOrder | None,
                  run: PoScore | None) -> str | None:
    if runner is None or run is None or run.amount_points < win.amount_points:
        return None
    fits = "exactly" if round(run.amount_points, 1) == config.PO_WEIGHT_AMOUNT else "better"
    return (f"{runner.po_id} fits the amount {fits}, but it's for {_lines_text(runner.lines)}; "
            f"the invoice is for {_lines_text(ctx.inv.lines)}.")


def _infer(ctx: RunContext, not_found_ref: str | None) -> StageResult:
    inv = ctx.inv
    survivors, log, remaining = _filter(ctx)
    details: dict = {"printed": not_found_ref, "elimination": log}
    ref_note = f"'{not_found_ref}' doesn't match any PO" if not_found_ref else None

    if not survivors:
        if ref_note:
            ctx.add("5.3", "hold", f"The PO reference {ref_note}, and no other open PO fits this invoice.",
                    ["AP", "Vendor"], details)
        ctx.add("5.9", "hold", f"No open PO for {ctx.vendor.name} fits this invoice. Please send the PO number.",
                ["Vendor", "Procurement"], details)
        return StageResult("warn", "No PO found", details)

    sims = similarity_table(ctx, needed_pairs(inv.lines, survivors, skip_exact=False))
    scores = sorted((score_po(ctx, po, sims, inv.total_paise, inv.invoice_date, remaining[po.po_id]) for po in survivors),
                    key=lambda s: s.total, reverse=True)
    by_id = {po.po_id: po for po in survivors}
    details.update({"scores": [s.as_dict() for s in scores], "similarity_source": sims.source})
    top = scores[0]
    second = scores[1] if len(scores) > 1 else None
    gap = top.total - (second.total if second else 0.0)
    details.update({"top": top.po_id, "gap": round(gap, 1)})

    if _spans_two_pos(ctx, survivors, sims):
        ctx.add("5.10", "hold", "The invoice lines match items on different POs. Split the invoice by PO.", ["AP"], details)
        return StageResult("warn", "Lines span more than one PO", details)

    if top.total >= config.PO_MATCH_MIN_SCORE and gap >= config.PO_MATCH_MIN_GAP:
        po = by_id[top.po_id]
        confidence = "High" if sims.source != SOURCE_TEXT else LOWER["High"]
        ctx.po, ctx.match_type, ctx.match_confidence = po, "Inferred", confidence
        _set_pairs(ctx, po, sims)
        sentence = _key_sentence(ctx, po, top, by_id.get(second.po_id) if second else None, second)
        details["explanation"] = sentence
        vs = f", vs {second.total:.1f} for {second.po_id}" if second else ""
        msg = f"No usable PO reference; matched {po.po_id} by its contents (score {top.total:.1f} of 100{vs})."
        if sims.source == SOURCE_TEXT:
            msg += " Descriptions were compared by text only, so confidence is lower."
        ctx.add("5.7", "pass", msg + (f" {sentence}" if sentence else ""), [], details)
        if ref_note:
            ctx.add("5.3", "hold", f"The PO reference {ref_note}; this invoice most likely belongs to {po.po_id}. "
                                   "Please confirm.", ["AP", "Vendor"], details)
        return StageResult("pass" if not ref_note else "warn",
                           f"Matched {po.po_id} (inferred, {confidence.lower()} confidence)", details)

    if ref_note:
        ctx.add("5.3", "hold", f"The PO reference {ref_note}.", ["AP", "Vendor"], details)
    if top.total >= config.PO_MATCH_MIN_SCORE:
        ctx.add("5.8", "hold", f"Two POs fit this invoice about equally well: {top.po_id} ({top.total:.1f}) and "
                               f"{second.po_id} ({second.total:.1f}). Please pick one.", ["AP"], details)
        return StageResult("warn", f"Two close candidates: {top.po_id}, {second.po_id}", details)
    ctx.add("5.9", "hold", f"No PO clearly fits this invoice (best is {top.po_id} at {top.total:.1f} of 100). "
                           "Please send the PO number.", ["Vendor", "Procurement"], details)
    return StageResult("warn", f"No confident match (best {top.po_id}, {top.total:.1f})", details)


def run(ctx: RunContext) -> StageResult:
    inv = ctx.inv
    raw_ref = (inv.po_reference or "").strip() or None
    year = (inv.invoice_date or ctx.today).year
    if raw_ref:
        result = _explicit(ctx, raw_ref, year)
        if result is not None:
            return result
    if ctx.vendor is None:
        if raw_ref:
            ctx.add("5.3", "hold", f"The PO reference '{raw_ref}' doesn't match any PO.", ["AP", "Vendor"],
                    {"printed": raw_ref, "tried": po_candidates_from_ref(raw_ref, year)})
        return StageResult("info", "Skipped: vendor unknown, so POs can't be filtered by vendor", {"printed": raw_ref})
    return _infer(ctx, raw_ref)
