import pytest

from app.models import Invoice, InvoiceLine, PurchaseOrder
from app.services.po import invoiced_qty, po_invoiced_paise, po_remaining_paise, po_total_paise
from app.utils.money import rupees_to_paise


def test_po_101_remaining_is_118000(db):
    po = db.get(PurchaseOrder, "PO-2026-101")
    assert po_total_paise(po) == rupees_to_paise(472000)
    assert po_invoiced_paise(db, po.po_id) == rupees_to_paise(354000)
    assert po_remaining_paise(db, po) == rupees_to_paise(118000)


def test_po_114_fully_billed(db):
    assert po_remaining_paise(db, db.get(PurchaseOrder, "PO-2026-114")) == 0


def test_po_104_total(db):
    assert po_total_paise(db.get(PurchaseOrder, "PO-2026-104")) == rupees_to_paise(148680)


# Totals from docs/SEED_KIT_README.md.
@pytest.mark.parametrize(
    "po_id,total,remaining",
    [
        ("PO-2026-101", 472000, 118000),
        ("PO-2026-104", 148680, 148680),
        ("PO-2026-117", 118000, 118000),
        ("PO-2026-105", 781160, 781160),
        ("PO-2026-116", 247800, 247800),
        ("PO-2026-108", 354000, 354000),
        ("PO-2026-109", 265500, 265500),
        ("PO-2026-110", 82600, 82600),
        ("PO-2026-112", 94400, 94400),
        ("PO-2026-114", 70800, 0),
    ],
)
def test_all_po_totals(db, po_id, total, remaining):
    po = db.get(PurchaseOrder, po_id)
    assert po_total_paise(po) == rupees_to_paise(total)
    assert po_remaining_paise(db, po) == rupees_to_paise(remaining)


def test_invoiced_qty(db):
    assert invoiced_qty(db, "PO-2026-101", 1) == 1500
    assert invoiced_qty(db, "PO-2026-114", 1) == 5000
    assert invoiced_qty(db, "PO-2026-104", 1) == 0


def test_exclude_run(db):
    po = db.get(PurchaseOrder, "PO-2026-101")
    assert po_remaining_paise(db, po, exclude_run="SEED-0002") == rupees_to_paise(118000 + 165200)
    assert invoiced_qty(db, "PO-2026-101", 1, exclude_run="SEED-0002") == 800


def test_only_approved_invoices_count(db):
    held = Invoice(
        run_id="RUN-TEST", po_id="PO-2026-104", vendor_id="V-01", decision="Hold",
        status="needs_review", total_paise=rupees_to_paise(118000),
    )
    held.lines = [InvoiceLine(line_no=1, description="Chair", qty=20, matched_po_line=1)]
    db.add(held)
    db.commit()
    po = db.get(PurchaseOrder, "PO-2026-104")
    assert po_remaining_paise(db, po) == rupees_to_paise(148680)
    assert invoiced_qty(db, "PO-2026-104", 1) == 0

    held.decision = "Approve"
    db.commit()
    assert po_remaining_paise(db, po) == rupees_to_paise(148680 - 118000)
    assert invoiced_qty(db, "PO-2026-104", 1) == 20
