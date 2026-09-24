"""Load backend/app/seed_data/*.json, auto-seed an empty DB, and reset demo data."""

import json
from datetime import date, datetime, time, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db import Base, engine
from app.models import (
    CompanySettings,
    GoodsReceipt,
    Invoice,
    InvoiceLine,
    PoLine,
    PurchaseOrder,
    TaxRate,
    Vendor,
)
from app.utils.normalise import norm_full

SEED_DIR = Path(__file__).resolve().parent / "seed_data"


def _load(name: str):
    return json.loads((SEED_DIR / name).read_text(encoding="utf-8"))


def _date(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def load_seed(db: Session) -> None:
    company = _load("company.json")
    db.add(CompanySettings(**company))

    for v in _load("vendors.json"):
        v = dict(v)
        v["short_name"] = v.pop("short", None)
        db.add(Vendor(**v))

    for r in _load("tax_rates.json"):
        db.add(TaxRate(**{**r, "valid_from": _date(r["valid_from"]), "valid_to": _date(r["valid_to"])}))

    for p in _load("purchase_orders.json"):
        p = dict(p)
        lines = p.pop("lines")
        po = PurchaseOrder(**{**p, "po_date": _date(p["po_date"])})
        po.lines = [PoLine(**line) for line in lines]
        db.add(po)
    db.flush()  # parents first: goods_receipts and invoices reference POs without a relationship

    for g in _load("goods_receipts.json"):
        db.add(GoodsReceipt(**{**g, "received_date": _date(g["received_date"])}))

    # Ledger: invoices approved before the app existed.
    for row in _load("ledger.json"):
        row = dict(row)
        lines = row.pop("lines")
        inv_date = _date(row["invoice_date"])
        stamp = datetime.combine(inv_date, time(10, 0), tzinfo=timezone.utc)
        inv = Invoice(
            **{**row, "invoice_date": inv_date},
            invoice_no_norm=norm_full(row["invoice_no"]),
            doc_type="invoice",
            processed_by="seed",
            created_at=stamp,
            finished_at=stamp,
        )
        inv.lines = [InvoiceLine(**line) for line in lines]
        db.add(inv)

    db.commit()


def is_empty(db: Session) -> bool:
    return db.scalar(select(CompanySettings.id).limit(1)) is None


def seed_if_empty(db: Session) -> bool:
    """Seed on startup when the database has no data. Returns True if it seeded."""
    if not is_empty(db):
        return False
    load_seed(db)
    return True


def reset(bind: Engine | None = None) -> None:
    """Drop every table, recreate it and load the seed data again."""
    from app import models  # noqa: F401

    bind = bind or engine
    Base.metadata.drop_all(bind)
    Base.metadata.create_all(bind)
    with Session(bind) as db:
        load_seed(db)
