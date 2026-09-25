"""One test per finding code used by samples 01-10, on small changes to the committed extractions."""

import pytest
from sqlalchemy import select

from app import llm
from app.config import BACKEND_DIR
from app.models import Invoice, RunStage
from app.pipeline import s1_read, s2_extract
from app.pipeline.runner import create_run, file_hash
from app.utils.gstin import gstin_checksum
from tests.helpers import SAMPLES, finding, run_rules, run_sample, sample_extraction

DECCAN = "01_happy_deccan.pdf"
INFERRED_ACME = "03_edge_inferred_po_acme.pdf"  # ACME/2026/0402, ₹1,18,000, PO-2026-104 (inferred), a chair
BRIGHTTECH = "06_edge_bank_changed_brighttech.pdf"


# --- stage 1-2 ------------------------------------------------------------------

def test_1_2_scan_detected(db):
    ctx = create_run(db, (SAMPLES / "02_happy_brighttech_scan.pdf").read_bytes(), "02.pdf")
    s1_read.run(ctx)
    f = finding(ctx, "1.2")
    assert ctx.is_scan and f.severity == "info" and f.audience == []


def test_1_4_quotation_rejected_to_vendor(db):
    ctx = create_run(db, (SAMPLES / "07_extra_quotation_acme.pdf").read_bytes(), "07.pdf")
    s1_read.run(ctx)
    s2_extract.run(ctx)
    f = finding(ctx, "1.4")
    assert ctx.halt and f.severity == "reject" and f.audience == ["Vendor"]


# --- stage 3 --------------------------------------------------------------------

def test_3_2_missing_date_holds_to_vendor(db):
    ex = sample_extraction(DECCAN)
    ex["invoice_date"] = None
    ctx = run_rules(db, ex)
    f = finding(ctx, "3.2")
    assert (f.severity, f.audience) == ("hold", ["Vendor"])
    assert ctx.decision == "Hold" and ctx.due_date is None


def test_3_2_unreadable_date_is_not_guessed(db):
    ex = sample_extraction(DECCAN)
    ex["invoice_date"] = "20/09/26?"
    ctx = run_rules(db, ex)
    assert "couldn't be read" in finding(ctx, "3.2").message
    assert ctx.due_date is None


def test_3_4_and_3_5_arithmetic(db):
    ex = sample_extraction(DECCAN)
    ex["subtotal"] = 230000.0  # lines add to 2,25,000
    ctx = run_rules(db, ex)
    assert "gap ₹5,000" in finding(ctx, "3.4").message
    assert finding(ctx, "3.5").severity == "hold"


def test_3_6_future_date(db):
    ex = sample_extraction(DECCAN)
    ex["invoice_date"] = "2026-10-01"
    assert finding(run_rules(db, ex), "3.6").severity == "hold"


# --- stage 4 --------------------------------------------------------------------

def test_4_5_blocked_vendor_rejects_to_procurement(db):
    ex = sample_extraction("10_extra_blocked_quickfix.pdf")
    ctx = run_rules(db, ex)
    f = finding(ctx, "4.5")
    assert (f.severity, f.audience) == ("reject", ["Procurement"])
    assert ctx.decision == "Reject"


def test_4_7_bank_changed_is_fraud_to_finance(db):
    ctx = run_rules(db, sample_extraction(BRIGHTTECH))
    f = finding(ctx, "4.7")
    assert f.severity == "hold" and f.fraud
    assert f.audience == ["Finance", "AP"]
    assert "…7766" in f.message and "…5667" in f.message


def test_4_3_invalid_gstin_falls_back_to_name(db):
    ex = sample_extraction(DECCAN)
    ex["vendor_gstin"] = "36AAKFD3456Q1ZX"  # bad checksum
    ctx = run_rules(db, ex)
    assert finding(ctx, "4.3").severity == "hold"
    assert finding(ctx, "4.2").severity == "info"
    assert ctx.vendor.vendor_id == "V-04"


def test_4_6_known_name_other_gstin_is_fraud(db):
    ex = sample_extraction(DECCAN)
    ex["vendor_gstin"] = "36AAKFD9999Q1Z" + gstin_checksum("36AAKFD9999Q1Z")  # valid, but not on file
    ctx = run_rules(db, ex)
    f = finding(ctx, "4.6")
    assert f.fraud and ctx.vendor is None


def test_4_4_unknown_vendor(db):
    ex = sample_extraction(DECCAN)
    ex["vendor_name"], ex["vendor_gstin"] = "Unheard Of Traders", None
    ctx = run_rules(db, ex)
    assert finding(ctx, "4.4").audience == ["Procurement"]


# --- stage 5 --------------------------------------------------------------------

def test_5_1_exact_reference(db):
    ctx = run_rules(db, sample_extraction(DECCAN))
    finding(ctx, "5.1")
    assert ctx.po.po_id == "PO-2026-109" and ctx.match_type == "Explicit"


@pytest.mark.parametrize("printed", ["PO 109", "PO109", "P.O. No: 2026/109", "Ref 2026-109"])
def test_5_2_reference_written_differently(db, printed):
    ex = sample_extraction(DECCAN)
    ex["po_reference"] = printed
    ctx = run_rules(db, ex)
    assert finding(ctx, "5.2").severity == "pass"
    assert ctx.po.po_id == "PO-2026-109"


def test_5_3_unknown_reference_falls_through_to_inference(db):
    ex = sample_extraction("03_edge_inferred_po_acme.pdf")
    ex["po_reference"] = "PO-2026-999"
    ctx = run_rules(db, ex)
    assert "likely belongs to PO-2026-104" in finding(ctx, "5.3").message
    assert ctx.po.po_id == "PO-2026-104" and ctx.decision == "Hold"


def test_5_5_po_of_another_vendor(db):
    ex = sample_extraction(DECCAN)
    ex["po_reference"] = "PO-2026-105"
    ctx = run_rules(db, ex)
    assert finding(ctx, "5.5").severity == "hold" and ctx.po is None


def test_5_4_closed_po(db):
    ex = sample_extraction("05_edge_duplicate_sahyadri_scan.pdf")
    ex["po_reference"] = "PO-2026-112"
    ex["invoice_number"] = "SPH/INV-0099"
    assert finding(run_rules(db, ex), "5.4").audience == ["Procurement"]


def test_5_7_inferred_match(db):
    ctx = run_rules(db, sample_extraction("03_edge_inferred_po_acme.pdf"))
    f = finding(ctx, "5.7")
    assert f.severity == "pass"
    assert (ctx.po.po_id, ctx.match_type, ctx.match_confidence) == ("PO-2026-104", "Inferred", "High")
    assert "PO-2026-117 fits the amount exactly" in f.message


# --- stage 6 --------------------------------------------------------------------

def test_6_5_and_6_6_overbilled_split(db):
    ctx = run_rules(db, sample_extraction("04_edge_split_overbill_acme.pdf"))
    f65, f66 = finding(ctx, "6.5"), finding(ctx, "6.6")
    assert "Only ₹1,18,000 remains on PO-2026-101; this invoice is ₹1,41,600." == f65.message
    assert [p["run_id"] for p in f65.evidence["previous_invoices"]] == ["SEED-0001", "SEED-0002"]
    assert "2,100 invoiced in total vs 2,000 ordered" in f66.message
    assert f65.audience == f66.audience == ["Vendor"]


def test_6_7_unit_price_above_po(db):
    ex = sample_extraction(DECCAN)
    ex["lines"][0]["unit_price"] = 19000.0  # PO says 18,000; tolerance 2% = 360
    assert "₹19,000 per unit vs ₹18,000" in finding(run_rules(db, ex), "6.7").message


def test_6_8_item_not_on_po(db):
    ex = sample_extraction(DECCAN)
    ex["lines"].append({"description": "Workstation desk 1400mm", "qty": 1, "unit_price": 1, "amount": 1, "tax_rate": 18})
    ex["lines"][1]["description"] = "Espresso machine"
    # "Espresso machine" has no identical PO line, so it needs a score; offline that's rapidfuzz.
    assert finding(run_rules(db, ex), "6.8").audience == ["Vendor", "Procurement"]


# --- stage 7 --------------------------------------------------------------------

def test_7_2_reformatted_number_of_approved_invoice_rejects(db):
    ctx = run_rules(db, sample_extraction("05_edge_duplicate_sahyadri_scan.pdf"))
    f = finding(ctx, "7.2")
    assert (f.severity, f.audience) == ("reject", ["Vendor", "AP"])
    assert f.evidence["duplicate_of"] == "SEED-0003"


def test_7_2_holds_when_original_not_approved(db):
    db.get(Invoice, "SEED-0003").decision = "Hold"
    db.commit()
    ctx = run_rules(db, sample_extraction("05_edge_duplicate_sahyadri_scan.pdf"))
    assert finding(ctx, "7.2").severity == "hold"


def test_7_4_same_amount_within_30_days(db):
    ex = sample_extraction("05_edge_duplicate_sahyadri_scan.pdf")
    ex["invoice_number"], ex["invoice_date"] = "SPH/INV-0077", "2026-09-15"
    assert finding(run_rules(db, ex), "7.4").audience == ["AP"]


def corrected_acme() -> dict:
    """ACME/2026/0417 corrected to ₹1,18,000: PO-2026-101, copier paper (page 1 of tests/data/two_invoices.pdf)."""
    cached = llm.load_cache(file_hash((BACKEND_DIR / "tests" / "data" / "two_invoices.pdf").read_bytes()))
    return cached.invoices[0].model_dump(mode="json")


def test_7_4_not_raised_for_a_different_po_and_different_items(db):
    first = run_sample(db, INFERRED_ACME)
    assert (first.decision, first.po.po_id) == ("Approve", "PO-2026-104")
    ctx = run_rules(db, corrected_acme())
    assert "7.4" not in ctx.codes() and ctx.decision == "Approve"
    stage = db.scalars(select(RunStage).where(RunStage.run_id == ctx.run_id, RunStage.stage_name == "Duplicates")).one()
    assert stage.status == "pass" and stage.details["duplicate_of"] == []
    assert stage.details["notes"] == [
        "Same amount as ACME/2026/0402, but a different PO and different items, so not a duplicate"]


def test_7_4_same_po_still_holds(db):
    first = run_sample(db, INFERRED_ACME)
    db.get(Invoice, first.run_id).po_id = "PO-2026-101"  # same PO as the corrected invoice; items still differ
    db.commit()
    ctx = run_rules(db, corrected_acme())
    assert finding(ctx, "7.4").evidence["invoice_no"] == "ACME/2026/0402" and ctx.decision == "Hold"


def test_7_4_invoice_without_a_po_still_holds(db):
    first = run_sample(db, INFERRED_ACME)
    db.get(Invoice, first.run_id).po_id = None  # say no PO could be matched for it
    db.commit()
    ctx = run_rules(db, corrected_acme())
    assert finding(ctx, "7.4").evidence["duplicate_of"] == first.run_id and ctx.decision == "Hold"


# --- stage 8 --------------------------------------------------------------------

def test_8_1_same_state_split(db):
    assert finding(run_rules(db, sample_extraction(DECCAN)), "8.1").severity == "pass"


def test_8_2_inter_state_igst(db):
    assert finding(run_rules(db, sample_extraction("02_happy_brighttech_scan.pdf")), "8.2").severity == "pass"


def test_8_3_wrong_split_holds_to_vendor(db):
    ctx = run_rules(db, sample_extraction("08_extra_wrong_split_brighttech.pdf"))
    f = finding(ctx, "8.3")
    assert (f.severity, f.audience) == ("hold", ["Vendor"])
    assert "Karnataka (29)" in f.message and "IGST applies" in f.message
    assert "8.2" not in ctx.codes()


def test_8_5_old_slab_after_cutoff(db):
    ex = sample_extraction(DECCAN)
    for ln in ex["lines"]:
        ln["tax_rate"] = 28.0
    assert "12% and 28% ended" in finding(run_rules(db, ex), "8.5").message


def test_8_6_wrong_tax_amount(db):
    ex = sample_extraction(DECCAN)
    ex["cgst"] = ex["sgst"] = 21000.0
    ex["total"] = 267000.0
    assert finding(run_rules(db, ex), "8.6").severity == "hold"


# --- stage 9 --------------------------------------------------------------------

def test_9_5_msme_cap(db):
    ctx = run_rules(db, sample_extraction(DECCAN))
    assert finding(ctx, "9.5").severity == "info"
    assert ctx.due_date.isoformat() == "2026-11-04"


def test_9_2_stale_invoice(db):
    ex = sample_extraction(DECCAN)
    ex["invoice_date"], ex["po_reference"] = "2026-02-01", None
    assert finding(run_rules(db, ex), "9.2").audience == ["AP"]
