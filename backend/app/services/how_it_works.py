"""Data for the "How it works" page: the case catalogue, a real PO-matching walkthrough and the GST rate history.

The walkthrough runs sample 03 through the real pipeline on a scratch copy of the seed data (like the test suite),
offline from the committed fixtures, so its numbers are whatever the code produces today, never copied from a doc.
"""

import threading
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import llm, seed
from app.db import make_engine
from app.models import PurchaseOrder, RunStage, TaxRate
from app.pipeline.catalogue import catalogue
from app.pipeline.runner import create_run, file_hash, run_pipeline
from app.services import runs as run_service
from app.services.po import po_remaining_paise, po_total_paise
from app.services.purchasing import rate_dict

WALKTHROUGH_SAMPLE = "03_edge_inferred_po_acme.pdf"
PO_STAGE = 5

_lock = threading.Lock()


def cases() -> dict:
    return catalogue()


def _po_row(db: Session, po: PurchaseOrder, run_id: str) -> dict:
    return {"po_id": po.po_id, "vendor": po.vendor.name, "status": po.status, "po_date": po.po_date.isoformat(),
            "total_paise": po_total_paise(po), "remaining_paise": po_remaining_paise(db, po, exclude_run=run_id),
            "lines": [{"description": ln.description, "qty": ln.qty, "unit_price_paise": ln.unit_price_paise}
                      for ln in po.lines]}


@lru_cache(maxsize=1)
def _walkthrough() -> dict:
    data = (run_service.SAMPLES_DIR / WALKTHROUGH_SAMPLE).read_bytes()
    if llm.load_cache(file_hash(data)) is None:  # never spend quota on an explainer
        raise LookupError("The walkthrough sample has no cached extraction.")
    engine = make_engine("sqlite://")
    try:
        seed.reset(engine)
        with Session(engine, autoflush=False, expire_on_commit=False) as db:
            ctx = create_run(db, data, WALKTHROUGH_SAMPLE, today=run_service.today())
            ctx.offline, ctx.send_emails = True, False
            run_pipeline(ctx, min_stage_ms=0)
            stage = db.scalars(select(RunStage).where(RunStage.run_id == ctx.run_id,
                                                      RunStage.stage_order == PO_STAGE)).one()
            d = stage.details or {}
            pos = {po.po_id: _po_row(db, po, ctx.run_id) for po in db.scalars(select(PurchaseOrder))}
            inv = ctx.inv
            return {
                "sample": WALKTHROUGH_SAMPLE,
                "invoice": {
                    "vendor": ctx.vendor.name if ctx.vendor else inv.vendor_name,
                    "invoice_no": inv.invoice_no,
                    "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
                    "total_paise": inv.total_paise,
                    "po_reference": inv.po_reference,
                    "lines": [{"description": ln.description, "qty": ln.qty, "unit_price_paise": ln.unit_price_paise}
                              for ln in inv.lines],
                },
                "elimination": [{**row, "po": pos.get(row["po_id"])} for row in d.get("elimination", [])],
                "scores": d.get("scores", []),
                "top": d.get("top"),
                "gap": d.get("gap"),
                "explanation": d.get("explanation"),
                "similarity_source": d.get("similarity_source"),
                "matched_po": ctx.po.po_id if ctx.po else None,
                "match_type": ctx.match_type,
                "match_confidence": ctx.match_confidence,
                "decision": ctx.decision,
                "stage_message": stage.message,
                "rules": catalogue()["rules"],
            }
    finally:
        engine.dispose()


def po_walkthrough() -> dict:
    """Stage 5 of sample 03, run once per process: the pipeline is deterministic on fixtures and seed data."""
    with _lock:
        return _walkthrough()


def tax_rates(db: Session, country: str = "IN") -> list[dict]:
    """Every GST rate with its dates, ended ones included, for the timeline."""
    rows = db.scalars(select(TaxRate).where(TaxRate.country == country).order_by(TaxRate.rate, TaxRate.valid_from))
    return [rate_dict(r) for r in rows]
