"""Case 1.6: a PDF holding several invoices becomes one child run per invoice.

Pages are assigned only on evidence, never guessed: the extraction's page ranges when they tile the document
exactly, else (text PDFs) one page per invoice when each invoice number is printed on exactly one page.
Anything else stays a 1.7 Hold. The runner creates the children; each is checked from stage 3 on its own.
"""

import hashlib
import io
import logging
import re

import pypdfium2 as pdfium
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Invoice, RunStage
from app.pipeline import s4_vendor
from app.pipeline.context import RunContext
from app.schemas import ExtractedInvoice
from app.utils.normalise import norm_full

log = logging.getLogger(__name__)

SPLIT = "split"  # the parent's status once its invoices are child runs; it has no decision of its own
FRAUD_CODES = {"4.6", "4.7"}
_TRAILER_ID = re.compile(rb"/ID\s*\[\s*<[0-9A-Fa-f]*>\s*<[0-9A-Fa-f]*>\s*\]")


def _range_pages(page_range: list[int]) -> list[int] | None:
    """[3] → page 3; [1, 2] or [1, 2, 3] → those pages. Anything else (gaps, reversed) isn't a range."""
    if not page_range:
        return None
    if len(page_range) == 2 and page_range[0] <= page_range[1]:
        return list(range(page_range[0], page_range[1] + 1))
    if page_range == list(range(page_range[0], page_range[0] + len(page_range))):
        return list(page_range)
    return None


def pages_from_ranges(invoices: list[ExtractedInvoice], page_count: int) -> list[list[int]] | None:
    """Each invoice's pages from its page_range, when every range is valid, none overlap and together they cover
    every page."""
    parts = [_range_pages(inv.page_range) for inv in invoices]
    if any(p is None for p in parts):
        return None
    seen: set[int] = set()
    for pages in parts:
        if any(p < 1 or p > page_count or p in seen for p in pages):
            return None
        seen.update(pages)
    return parts if seen == set(range(1, page_count + 1)) else None


def pages_from_text(invoices: list[ExtractedInvoice], page_texts: list[str]) -> list[list[int]] | None:
    """One page each, when there are as many invoices as pages and each invoice number is on exactly one page."""
    if len(invoices) != len(page_texts):
        return None
    texts = [norm_full(t) for t in page_texts]
    parts = []
    for inv in invoices:
        number = norm_full(inv.invoice_number)
        hits = [i for i, t in enumerate(texts) if number and number in t]
        if len(hits) != 1:
            return None
        parts.append([hits[0] + 1])
    return parts if len({p[0] for p in parts}) == len(parts) else None


def assign_pages(invoices: list[ExtractedInvoice], page_count: int, page_texts: list[str],
                 boundaries_clear: bool) -> list[list[int]] | None:
    """Pages per invoice (same order as `invoices`), or None when they can't be assigned with confidence."""
    return (pages_from_ranges(invoices, page_count) if boundaries_clear else None) or \
        pages_from_text(invoices, page_texts)


def pages_label(pages: list[int]) -> str:
    return f"page {pages[0]}" if len(pages) == 1 else f"pages {pages[0]}–{pages[-1]}"


def cut_pages(file_bytes: bytes, pages: list[int], parent_hash: str) -> bytes:
    """A new PDF of just these pages (1-based). The same file and pages always give the same bytes, so a re-upload
    of the combined file is caught as the same file (7.1)."""
    src = pdfium.PdfDocument(file_bytes)
    out = pdfium.PdfDocument.new()
    try:
        out.import_pages(src, [p - 1 for p in pages])
        buf = io.BytesIO()
        out.save(buf)
    finally:
        out.close()
        src.close()
    # pdfium stamps a random document ID; replace it (same length, so the xref offsets hold) with one from the input.
    stable = hashlib.md5(f"{parent_hash}:{pages}".encode()).hexdigest().upper().encode()
    return _TRAILER_ID.sub(b"/ID[<" + stable + b"><" + stable + b">]", buf.getvalue(), count=1)


def split_origin(db: Session, run_id: str) -> dict | None:
    """For a child run: where it came from (parent run, its pages, the parent's page count), from its stage 1 row."""
    details = db.scalar(select(RunStage.details).where(RunStage.run_id == run_id, RunStage.stage_order == 1))
    if not details or not details.get("split_from"):
        return None
    return {"run_id": details["split_from"], "pages": details.get("source_pages") or [],
            "page_count": details.get("source_page_count"), "part": details.get("part"), "parts": details.get("parts")}


def _stored_fraud(db: Session, run_id: str) -> bool | None:
    """Whether the run's own vendor check found fraud; None if it hasn't run stage 4 yet."""
    stages = db.scalars(select(RunStage).where(RunStage.run_id == run_id)).all()
    if not any(s.stage_order >= 4 for s in stages):
        return None
    return any(f.get("fraud") and f.get("code") in FRAUD_CODES for s in stages for f in (s.details or {}).get("findings", []))


def _vendor_check_fraud(db: Session, sibling: Invoice) -> bool:
    """Stage 4's own rules on a sibling that hasn't been checked yet. They read only the vendor master, so the answer
    is the one its run will get."""
    ctx = RunContext(run_id=sibling.run_id, file_bytes=b"", file_hash="", company=None, db=db,
                     extraction=sibling.extraction)
    s4_vendor.run(ctx)
    return any(f.fraud and f.code in FRAUD_CODES for f in ctx.findings)


def sibling_fraud(db: Session, run_id: str) -> list[str]:
    """The other invoices from the same split file that have a fraud finding. Empty for any other run."""
    me = db.get(Invoice, run_id)
    parent = db.get(Invoice, me.parent_upload_id) if me is not None and me.parent_upload_id else None
    if parent is None or parent.status != SPLIT:
        return []
    siblings = db.scalars(select(Invoice).where(Invoice.parent_upload_id == parent.run_id, Invoice.run_id != run_id)
                          .order_by(Invoice.created_at, Invoice.run_id)).all()
    hits = []
    for s in siblings:
        fraud = _stored_fraud(db, s.run_id)
        if fraud is None:
            try:
                fraud = _vendor_check_fraud(db, s)
            except Exception:  # the sibling's own run reports what went wrong; this run carries on
                log.exception("vendor pre-check of sibling %s failed", s.run_id)
                fraud = False
        if fraud:
            hits.append(s.run_id)
    return hits
