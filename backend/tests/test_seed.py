from sqlalchemy.orm import Session

from app.models import (
    CompanySettings,
    GoodsReceipt,
    Invoice,
    InvoiceLine,
    PurchaseOrder,
    TaxRate,
    Vendor,
)
from app.seed import reset, seed_if_empty


def test_row_counts(db):
    assert db.query(CompanySettings).count() == 1
    assert db.query(Vendor).count() == 6
    assert db.query(TaxRate).count() == 7
    assert db.query(PurchaseOrder).count() == 10
    assert db.query(GoodsReceipt).count() == 10
    assert db.query(Invoice).count() == 3
    assert db.query(InvoiceLine).count() == 3


def test_ledger_rows_are_seed_and_approved(db):
    for inv in db.query(Invoice):
        assert inv.is_seed is True
        assert inv.decision == "Approve"
        assert inv.status == "approved"
    sph = db.get(Invoice, "SEED-0003")
    assert sph.invoice_no_norm == "SPHINV0042"
    assert sph.lines[0].qty == 5000


def test_vendor_extra_fields(db):
    v = db.get(Vendor, "V-02")
    assert v.short_name == "BrightTech Solutions"
    assert v.phone
    assert db.get(Vendor, "V-06").status == "Blocked"
    assert db.get(Vendor, "V-04").msme is True


def test_seed_if_empty_is_idempotent(db):
    assert seed_if_empty(db) is False
    assert db.query(Vendor).count() == 6


def test_reset_restores_data(engine):
    with Session(engine) as s:
        s.get(PurchaseOrder, "PO-2026-104").status = "Closed"
        s.delete(s.get(Invoice, "SEED-0001"))
        s.commit()
    reset(engine)
    with Session(engine) as s:
        assert s.get(PurchaseOrder, "PO-2026-104").status == "Open"
        assert s.get(Invoice, "SEED-0001") is not None
