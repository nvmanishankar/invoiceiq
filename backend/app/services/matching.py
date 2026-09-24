"""Description similarity and PO scoring for stage 5 (build guide section 9).

The LLM only scores how alike two descriptions are. Pairing, points and the match
decision are rules here and in s5_po_match.
"""

from dataclasses import dataclass, field
from datetime import date

from rapidfuzz import fuzz, utils

from app import config, llm
from app.models import PurchaseOrder
from app.pipeline.context import InvLine, LinePair, RunContext
from app.services.po import invoiced_qty, po_remaining_paise
from app.utils.money import within_tolerance
from app.utils.normalise import text_key

SOURCE_LLM = "llm"
SOURCE_TEXT = "text match"  # rapidfuzz fallback


def fuzzy_similarity(a: str, b: str) -> float:
    return fuzz.token_set_ratio(a, b, processor=utils.default_process) / 100


@dataclass
class SimTable:
    """Similarity for (invoice description, PO description) pairs, and where it came from."""

    scores: dict[tuple[str, str], float] = field(default_factory=dict)
    source: str = SOURCE_LLM  # SOURCE_TEXT if any score came from the fallback

    def get(self, a: str, b: str) -> float:
        return self.scores.get((a, b), 0.0)


def similarity_table(ctx: RunContext, pairs: list[tuple[str, str]]) -> SimTable:
    """Identical text scores 1.0 without asking anyone; the rest go to one batched LLM call.

    If the LLM can't answer, every remaining pair is scored with rapidfuzz instead.
    """
    table = SimTable()
    ask: list[tuple[str, str]] = []
    for a, b in dict.fromkeys(pairs):  # unique, order kept
        if text_key(a) and text_key(a) == text_key(b):
            table.scores[(a, b)] = 1.0
        else:
            ask.append((a, b))
    if not ask:
        return table
    ask.sort()  # stable order → stable cache key
    scores = llm.similarity(ask, ctx)
    if scores is None:
        table.source = SOURCE_TEXT
        scores = [fuzzy_similarity(a, b) for a, b in ask]
    table.scores.update(zip(ask, scores))
    return table


def pair_lines(inv_lines: list[InvLine], po: PurchaseOrder, sims: SimTable) -> tuple[list[LinePair], list[InvLine]]:
    """Each invoice line goes to its most similar PO line, if that similarity counts."""
    pairs, unpaired = [], []
    for il in inv_lines:
        best = max(po.lines, key=lambda pl: sims.get(il.description, pl.description), default=None)
        s = sims.get(il.description, best.description) if best else 0.0
        if best is not None and s >= config.PO_DESC_MIN_SIM:
            pairs.append(LinePair(il, best, s))
        else:
            unpaired.append(il)
    return pairs, unpaired


def needed_pairs(inv_lines: list[InvLine], pos: list[PurchaseOrder], skip_exact: bool) -> list[tuple[str, str]]:
    """Pairs that need a similarity score.

    With skip_exact (explicit PO), an invoice line whose text equals a PO line needs nothing else.
    """
    out = []
    for po in pos:
        for il in inv_lines:
            exact = [pl for pl in po.lines if text_key(pl.description) == text_key(il.description)] if skip_exact else []
            out.extend((il.description, pl.description) for pl in (exact[:1] or po.lines))
    return out


@dataclass
class PoScore:
    po_id: str
    line_points: float
    amount_points: float
    date_points: float
    line_detail: list[dict]

    @property
    def total(self) -> float:
        return round(self.line_points + self.amount_points + self.date_points, 1)

    def as_dict(self) -> dict:
        return {"po_id": self.po_id, "lines": round(self.line_points, 1), "amount": round(self.amount_points, 1),
                "date": round(self.date_points, 1), "total": self.total, "line_detail": self.line_detail}


def score_po(ctx: RunContext, po: PurchaseOrder, sims: SimTable, total_paise: int | None,
             inv_date: date | None, remaining_paise: int | None = None) -> PoScore:
    """Line items (50) + amount fit (30) + date proximity (20). Weights live in config."""
    tol_pct, tol_abs = ctx.company.tolerance_pct, ctx.company.tolerance_abs_paise
    pts, detail = [], []
    for il in ctx.inv.lines:
        best = max(po.lines, key=lambda pl: sims.get(il.description, pl.description), default=None)
        s = sims.get(il.description, best.description) if best else 0.0
        if best is None or s < config.PO_DESC_MIN_SIM:
            pts.append(0.0)
            detail.append({"invoice_line": il.description, "po_line": best.description if best else None,
                           "similarity": round(s, 2), "counts": False})
            continue
        open_qty = best.qty - invoiced_qty(ctx.db, po.po_id, best.line_no, exclude_run=ctx.run_id)
        qty_ok = il.qty is not None and il.qty <= open_qty
        price_ok = il.unit_price_paise is not None and within_tolerance(
            il.unit_price_paise, best.unit_price_paise, tol_pct, tol_abs)
        pts.append(config.PO_LINE_SHARE_SIM * s + config.PO_LINE_SHARE_QTY * qty_ok
                   + config.PO_LINE_SHARE_PRICE * price_ok)
        detail.append({"invoice_line": il.description, "po_line": best.description, "similarity": round(s, 2),
                       "counts": True, "qty_ok": qty_ok, "price_ok": price_ok})
    line_points = config.PO_WEIGHT_LINES * (sum(pts) / len(pts)) if pts else 0.0

    remaining = po_remaining_paise(ctx.db, po, exclude_run=ctx.run_id) if remaining_paise is None else remaining_paise
    if total_paise and remaining > 0:
        amount_points = config.PO_WEIGHT_AMOUNT * min(total_paise, remaining) / max(total_paise, remaining)
    else:
        amount_points = 0.0

    if inv_date is not None:
        days = (inv_date - po.po_date).days
        date_points = config.PO_WEIGHT_DATE * max(0.0, 1 - days / config.PO_DATE_WINDOW_DAYS) if days >= 0 else 0.0
    else:
        date_points = 0.0
    return PoScore(po.po_id, line_points, amount_points, date_points, detail)
