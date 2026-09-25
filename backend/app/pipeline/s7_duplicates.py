"""Stage 7: duplicates against earlier runs (cases 7.1-7.5)."""

from sqlalchemy import select

from app.config import NEAR_DUPLICATE_DAYS
from app.models import Invoice
from app.pipeline.context import RunContext, StageResult, summarise
from app.services.po import APPROVED

SUPERSEDED = "superseded"  # services.review.SUPERSEDED; imported from there it would be circular
SPLIT = "split"  # pipeline.split.SPLIT: the combined file itself isn't an invoice to compare against
from app.utils.money import format_inr
from app.utils.normalise import core_number, norm_full


def _when(d) -> str:
    return f"{d:%d %b %Y}" if d else "an unknown date"


def _prior_state(prior: Invoice) -> str:
    return "already approved" if prior.decision == APPROVED else f"still open ({(prior.decision or 'in progress').lower()})"


def run(ctx: RunContext) -> StageResult:
    inv = ctx.inv
    before = len(ctx.findings)
    linked: list[str] = []
    # A corrected invoice isn't a duplicate of the run it replaces, nor of any run a correction already replaced.
    me = ctx.db.get(Invoice, ctx.run_id)
    skip = [ctx.run_id] + ([me.parent_upload_id] if me is not None and me.parent_upload_id else [])
    live = (Invoice.run_id.not_in(skip), Invoice.status.not_in((SUPERSEDED, SPLIT)))

    # 7.1: this exact file, any vendor. Rejected runs don't count: a rejected file may be sent again.
    same_file = ctx.db.scalars(select(Invoice).where(
        Invoice.file_hash == ctx.file_hash, *live,
        Invoice.decision.is_not(None), Invoice.decision != "Reject").order_by(Invoice.created_at)).first()
    if same_file is not None:
        sev = "reject" if same_file.decision == APPROVED else "hold"
        ctx.add("7.1", sev, f"This exact file was already processed as {same_file.run_id}, which is "
                            f"{_prior_state(same_file)}.", ["AP"], {"duplicate_of": same_file.run_id})
        linked.append(same_file.run_id)

    priors = [] if ctx.vendor is None else ctx.db.scalars(select(Invoice).where(
        Invoice.vendor_id == ctx.vendor.vendor_id, *live,
        Invoice.decision.is_not(None), Invoice.decision != "Reject").order_by(Invoice.invoice_date)).all()
    no_full, no_core = norm_full(inv.invoice_no), core_number(inv.invoice_no)
    for prior in priors:
        if prior.run_id in linked:
            continue
        same_number = bool(inv.invoice_no) and (
            (no_full and norm_full(prior.invoice_no) == no_full) or (no_core and core_number(prior.invoice_no) == no_core))
        same_total = inv.total_paise is not None and prior.total_paise == inv.total_paise
        same_date = inv.invoice_date is not None and prior.invoice_date == inv.invoice_date
        sev = "reject" if prior.decision == APPROVED else "hold"
        evidence = {"duplicate_of": prior.run_id, "invoice_no": prior.invoice_no,
                    "invoice_date": prior.invoice_date.isoformat() if prior.invoice_date else None,
                    "total_paise": prior.total_paise, "decision": prior.decision}
        if same_number and (same_total or same_date):
            ctx.add("7.2", sev, f"This is the same invoice as {prior.invoice_no} dated {_when(prior.invoice_date)} "
                                f"({prior.run_id}), which is {_prior_state(prior)}.", ["Vendor", "AP"], evidence)
            linked.append(prior.run_id)
        elif same_total and same_date:
            ctx.add("7.3", sev, f"Same amount ({format_inr(prior.total_paise)}) and date as {prior.invoice_no} "
                                f"({prior.run_id}), which is {_prior_state(prior)}. Likely a re-scanned copy.",
                    ["Vendor", "AP"], evidence)
            linked.append(prior.run_id)
        elif same_total and inv.invoice_date and prior.invoice_date \
                and abs((prior.invoice_date - inv.invoice_date).days) <= NEAR_DUPLICATE_DAYS:
            ctx.add("7.4", "hold", f"Same amount ({format_inr(prior.total_paise)}) as {prior.invoice_no} from "
                                   f"{_when(prior.invoice_date)} ({prior.run_id}). Possible duplicate.", ["AP"], evidence)
            linked.append(prior.run_id)

    new = ctx.findings[before:]
    details = {"checked": len(priors), "duplicate_of": linked}
    if any(f.severity == "reject" for f in new):
        return StageResult("fail", new[0].message, details)
    if new:
        return StageResult("warn", summarise(new), details)
    if ctx.vendor is None:
        return StageResult("info", "Skipped: vendor unknown, so only the file itself was checked", details)
    return StageResult("pass", f"No duplicate among {len(priors)} earlier invoice(s) from {ctx.vendor.name}", details)
