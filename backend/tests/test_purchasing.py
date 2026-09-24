"""Phase 12: purchase orders, vendors, tax rates, settings and role checks, offline."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import seed
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Alert, CompanySettings
from app.services import runs as run_service
from app.utils.gstin import gstin_checksum
from app.utils.money import rupees_to_paise
from tests.helpers import TODAY, run_rules, run_sample

PROCUREMENT = {"X-Role": "Procurement"}
NEW_GSTIN = "29AAKCN4455P1Z" + gstin_checksum("29AAKCN4455P1Z")  # Karnataka, so IGST from Telangana


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "MIN_STAGE_MS", 0)
    monkeypatch.setattr(run_service, "today", lambda: TODAY)
    seed.reset()
    with TestClient(app) as c:
        yield c


def laptop_po(vendor_id="V-02", **over) -> dict:
    """The design doc's example: 10 laptops and 10 backpacks, 18% GST, Net 45."""
    body = {
        "vendor_id": vendor_id, "po_date": "2026-09-20", "payment_terms_days": 45, "department": "IT",
        "lines": [
            {"description": "Dell Latitude 5440 laptop, i5, 16GB", "hsn_code": "8471", "qty": 10, "unit": "pcs",
             "unit_price": 65000, "tax_rate": 18},
            {"description": "Laptop backpack, 15.6 inch", "qty": 10, "unit": "pcs", "unit_price": 1200, "tax_rate": 18},
        ],
    }
    return {**body, **over}


def new_vendor(**over) -> dict:
    body = {"name": "Nandi Computers Private Limited", "short_name": "Nandi Computers", "gstin": NEW_GSTIN,
            "bank_account": "4455 6677 8899", "ifsc": "sbin0004411", "contact_email": "accounts@nandi.example",
            "phone": "+91 80 4000 1234", "msme": False}
    return {**body, **over}


# --- Purchase orders ------------------------------------------------------------------------------------------------

def test_create_po_numbers_in_sequence_and_totals(client):
    assert client.get("/api/pos/next-id").json()["po_id"] == "PO-2026-119"

    r = client.post("/api/pos", json=laptop_po(), headers=PROCUREMENT)
    assert r.status_code == 201, r.text
    po = r.json()
    assert po["po_id"] == "PO-2026-119" and po["status"] == "Open" and po["created_by"] == "Procurement"
    assert po["tax_type"] == "IGST"
    assert po["subtotal_paise"] == rupees_to_paise(662000)
    assert po["igst_paise"] == rupees_to_paise(119160) and po["cgst_paise"] == 0
    assert po["total_display"] == "₹7,81,160" and po["remaining_paise"] == po["total_paise"]
    assert [ln["unit_price_paise"] for ln in po["lines"]] == [6500000, 120000]
    assert po["lines"][1]["hsn_code"] is None and po["warnings"] == []

    second = client.post("/api/pos", json=laptop_po(), headers=PROCUREMENT).json()
    assert second["po_id"] == "PO-2026-120"
    assert {p["po_id"] for p in client.get("/api/pos").json()} >= {"PO-2026-119", "PO-2026-120"}


def test_same_state_vendor_splits_cgst_sgst(client):
    po = client.post("/api/pos", json=laptop_po("V-01"), headers=PROCUREMENT).json()
    assert po["tax_type"] == "CGST+SGST"
    assert po["cgst_paise"] == po["sgst_paise"] == rupees_to_paise(59580) and po["igst_paise"] == 0


@pytest.mark.parametrize("change,field,words", [
    ({"vendor_id": None}, "vendor_id", "Choose a vendor"),
    ({"vendor_id": "V-99"}, "vendor_id", "no vendor V-99"),
    ({"vendor_id": "V-06"}, "vendor_id", "blocked"),
    ({"po_date": "2026-09-25"}, "po_date", "can't be in the future"),
    ({"po_date": "20/09/2026"}, "po_date", "YYYY-MM-DD"),
    ({"payment_terms_days": -1}, "payment_terms_days", "0 to 365"),
    ({"lines": []}, "lines", "at least one line"),
])
def test_create_po_refuses_bad_headers(client, change, field, words):
    r = client.post("/api/pos", json=laptop_po(**change), headers=PROCUREMENT)
    assert r.status_code == 422, r.text
    assert words in r.json()["errors"][field] and r.json()["detail"]


@pytest.mark.parametrize("change,field,words", [
    ({"description": "  "}, "description", "describe the item"),
    ({"qty": 0}, "qty", "more than 0"),
    ({"unit_price": 0}, "unit_price", "more than ₹0"),
    ({"unit_price": 0.001}, "unit_price", "more than ₹0"),
    ({"unit": ""}, "unit", "choose a unit"),
    ({"hsn_code": "84A1"}, "hsn_code", "4, 6 or 8 digits"),
    ({"tax_rate": 12}, "tax_rate", "12% isn't a valid GST rate on 20 Sep 2026"),
    ({"tax_rate": None}, "tax_rate", "choose a tax rate"),
])
def test_create_po_refuses_bad_lines(client, change, field, words):
    body = laptop_po()
    body["lines"][1] = {**body["lines"][1], **change}
    r = client.post("/api/pos", json=body, headers=PROCUREMENT)
    assert r.status_code == 422, r.text
    assert words in r.json()["errors"][f"lines.1.{field}"]


def test_tax_rate_must_be_valid_on_the_po_date(client):
    old = laptop_po(po_date="2025-09-01")
    old["lines"][0]["tax_rate"] = 28  # the old slab, still in force until 21 Sep 2025
    assert client.post("/api/pos", json=old, headers=PROCUREMENT).status_code == 201

    early = laptop_po(po_date="2025-09-01")
    early["lines"][0]["tax_rate"] = 40  # the demerit slab starts 22 Sep 2025
    r = client.post("/api/pos", json=early, headers=PROCUREMENT)
    assert r.status_code == 422 and "40%" in r.json()["errors"]["lines.0.tax_rate"]


def test_tax_rates_endpoint_lists_slabs_in_force(client):
    now = client.get("/api/tax-rates", params={"country": "IN", "on": "2026-09-24"}).json()
    assert [r["rate"] for r in now] == [0, 3, 5, 18, 40]
    before = client.get("/api/tax-rates", params={"on": "2025-09-21"}).json()
    assert [r["rate"] for r in before] == [0, 3, 5, 12, 18, 28]
    assert [r["rate"] for r in client.get("/api/tax-rates").json()] == [0, 3, 5, 18, 40]  # today


def test_msme_terms_over_45_days_warn_but_save(client):
    r = client.post("/api/pos", json=laptop_po("V-04", payment_terms_days=60), headers=PROCUREMENT)
    assert r.status_code == 201
    assert "MSME" in r.json()["warnings"][0] and "45 days" in r.json()["warnings"][0]


@pytest.mark.parametrize("headers", [{}, {"X-Role": "AP clerk"}, {"X-Role": "Finance"}, {"X-Role": "Admin"}])
def test_only_procurement_changes_pos_and_vendors(client, headers):
    for method, path, body in [
        ("post", "/api/pos", laptop_po()),
        ("patch", "/api/pos/PO-2026-104", {"status": "Closed"}),
        ("post", "/api/vendors", new_vendor()),
        ("patch", "/api/vendors/V-01", {"status": "Blocked"}),
    ]:
        r = getattr(client, method)(path, json=body, headers=headers)
        assert r.status_code == 403, (path, r.text)
        assert "Only Procurement" in r.json()["detail"] and "segregation of duties" in r.json()["detail"]
    assert client.get("/api/pos/next-id").json()["po_id"] == "PO-2026-119"  # nothing was created
    assert client.get("/api/pos/PO-2026-104").json()["status"] == "Open"


def test_register_shows_balances_and_billed_invoices(client):
    pos = {p["po_id"]: p for p in client.get("/api/pos").json()}
    p101 = pos["PO-2026-101"]
    assert p101["total_display"] == "₹4,72,000" and p101["invoiced_display"] == "₹3,54,000"
    assert p101["remaining_display"] == "₹1,18,000"
    assert [i["invoice_no"] for i in p101["invoices"]] == ["ACME/2026/0311", "ACME/2026/0388"]
    assert p101["lines"][0]["invoiced_qty"] == 1500
    assert pos["PO-2026-114"]["remaining_paise"] == 0
    assert pos["PO-2026-112"]["status"] == "Closed"
    assert p101["vendor_state"] == "Telangana (36)" and p101["tax_type"] == "CGST+SGST"


def test_register_counts_only_approved_invoices(client):
    held = client.post("/api/runs", json={"sample_name": "04_edge_split_overbill_acme.pdf"}).json()["run_id"]
    p101 = next(p for p in client.get("/api/pos").json() if p["po_id"] == "PO-2026-101")
    billed = {i["run_id"]: i for i in p101["invoices"]}
    assert billed[held]["decision"] == "Hold" and not billed[held]["counts_against_po"]
    assert p101["remaining_display"] == "₹1,18,000"


def test_close_and_reopen_po_changes_the_next_run(client):
    r = client.patch("/api/pos/PO-2026-109", json={"status": "Closed"}, headers=PROCUREMENT)
    assert r.status_code == 200 and r.json()["status"] == "Closed"
    with SessionLocal() as s:
        ctx = run_sample(s, "01_happy_deccan.pdf")
    assert ctx.decision == "Hold" and "5.4" in ctx.codes()

    assert client.patch("/api/pos/PO-2026-109", json={"status": "Open"}, headers=PROCUREMENT).json()["status"] == "Open"
    assert client.patch("/api/pos/PO-2026-999", json={"status": "Open"}, headers=PROCUREMENT).status_code == 404
    assert client.patch("/api/pos/PO-2026-109", json={"status": "Cancelled"}, headers=PROCUREMENT).status_code == 422


# --- Vendors --------------------------------------------------------------------------------------------------------

def test_add_vendor_derives_state_and_masks_bank(client):
    r = client.post("/api/vendors", json=new_vendor(), headers=PROCUREMENT)
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["vendor_id"] == "V-07" and v["status"] == "Active" and v["created_by"] == "Procurement"
    assert v["gstin"] == NEW_GSTIN and v["state"] == "Karnataka (29)" and v["ifsc"] == "SBIN0004411"
    assert v["bank_last4"] == "8899" and v["msme"] is False
    listed = {x["vendor_id"]: x for x in client.get("/api/vendors").json()}
    assert "V-07" in listed and "bank_account" not in listed["V-07"]
    assert listed["V-01"]["bank_masked"] == "…4521" and listed["V-01"]["open_pos"] == 3


@pytest.mark.parametrize("gstin,words", [
    ("", "Enter the vendor's GSTIN"),
    ("29AAKCN4455P1Z", "15 characters; this one has 14"),
    ("29AAKCN4455P1X" + "1", "That isn't a GSTIN"),
    ("25AAKCN4455P1Z" + gstin_checksum("25AAKCN4455P1Z"), "isn't an Indian state code"),
    (NEW_GSTIN[:14] + ("A" if NEW_GSTIN[14] != "A" else "B"), "check character doesn't match"),
])
def test_add_vendor_refuses_bad_gstin(client, gstin, words):
    r = client.post("/api/vendors", json=new_vendor(gstin=gstin), headers=PROCUREMENT)
    assert r.status_code == 422, r.text
    assert words in r.json()["errors"]["gstin"]


@pytest.mark.parametrize("change,field,words", [
    ({"name": " "}, "name", "legal name"),
    ({"ifsc": "HDFC1234567"}, "ifsc", "4 letters for the bank, a zero"),
    ({"bank_account": "12-34"}, "bank_account", "9 to 18 digits"),
    ({"contact_email": ""}, "contact_email", "Enter a contact email"),
    ({"contact_email": "accounts"}, "contact_email", "doesn't look like an email"),
    ({"msme": None}, "msme", "MSME"),
])
def test_add_vendor_checks_each_field(client, change, field, words):
    r = client.post("/api/vendors", json=new_vendor(**change), headers=PROCUREMENT)
    assert r.status_code == 422 and words in r.json()["errors"][field]


def test_add_vendor_refuses_duplicate_gstin(client):
    acme = "36AABCA1234F1ZA"
    r = client.post("/api/vendors", json=new_vendor(gstin=acme), headers=PROCUREMENT)
    assert r.status_code == 409
    assert r.json()["errors"]["gstin"] == "This GSTIN already belongs to Acme Supplies Private Limited (V-01)."


def test_add_vendor_refuses_duplicate_bank_account(client):
    r = client.post("/api/vendors", json=new_vendor(bank_account="9120 1004 455667"), headers=PROCUREMENT)
    assert r.status_code == 409
    msg = r.json()["errors"]["bank_account"]
    assert "BrightTech Solutions Pvt Ltd (V-02)" in msg and "fraud signal" in msg
    assert len(client.get("/api/vendors").json()) == 6


def test_block_and_unblock_vendor(client):
    r = client.patch("/api/vendors/V-04", json={"status": "Blocked"}, headers=PROCUREMENT)
    assert r.status_code == 200 and r.json()["status"] == "Blocked"
    with SessionLocal() as s:
        blocked = run_sample(s, "01_happy_deccan.pdf")
    assert blocked.decision == "Reject" and "4.5" in blocked.codes()
    assert client.post("/api/pos", json=laptop_po("V-04"), headers=PROCUREMENT).status_code == 422

    assert client.patch("/api/vendors/V-04", json={"status": "Active"}, headers=PROCUREMENT).json()["status"] == "Active"
    with SessionLocal() as s:  # a rejected file may be sent again, so this isn't a duplicate
        assert run_sample(s, "01_happy_deccan.pdf").decision == "Approve"
    assert client.patch("/api/vendors/V-99", json={"status": "Active"}, headers=PROCUREMENT).status_code == 404


# --- A new vendor and PO flow through the pipeline ------------------------------------------------------------------

def invoice_for_new_po(po_id: str) -> dict:
    return {
        "vendor_name": "Nandi Computers Private Limited", "vendor_gstin": NEW_GSTIN,
        "invoice_number": "NC/26/0042", "invoice_date": "2026-09-22", "po_reference": po_id, "currency": "INR",
        "lines": [
            {"description": "Dell Latitude 5440 laptop, i5, 16GB", "hsn": "8471", "qty": 10, "unit": "pcs",
             "unit_price": 65000, "tax_rate": 18, "amount": 650000},
            {"description": "Laptop backpack, 15.6 inch", "qty": 10, "unit": "pcs", "unit_price": 1200,
             "tax_rate": 18, "amount": 12000},
        ],
        "subtotal": 662000, "cgst": None, "sgst": None, "igst": 119160, "total": 781160, "tax_inclusive": False,
        "bank_account": "445566778899", "ifsc": "SBIN0004411", "payment_terms_days": 45,
        "confidence": {k: "high" for k in ("invoice_number", "invoice_date", "total", "vendor_gstin", "bank_account",
                                           "po_reference")},
    }


def test_new_vendor_and_po_are_matched_and_approved(client):
    assert client.post("/api/vendors", json=new_vendor(), headers=PROCUREMENT).status_code == 201
    po = client.post("/api/pos", json=laptop_po("V-07"), headers=PROCUREMENT).json()
    assert po["po_id"] == "PO-2026-119"

    with SessionLocal() as s:
        ctx = run_rules(s, invoice_for_new_po(po["po_id"]))
    assert ctx.decision == "Approve", [(f.code, f.message) for f in ctx.findings]
    assert ctx.po.po_id == "PO-2026-119" and ctx.vendor.vendor_id == "V-07"
    assert {"4.1", "5.1", "6.1", "8.2"} <= set(ctx.codes())
    assert str(ctx.due_date) == "2026-11-06"  # 45 days, the PO's terms

    (billed,) = client.get("/api/pos/PO-2026-119").json()["invoices"]  # run_rules skips stage 2, so no totals
    assert billed["run_id"] == ctx.run_id and billed["decision"] == "Approve" and billed["counts_against_po"]


# --- Settings -------------------------------------------------------------------------------------------------------

def test_settings_read_and_update(client):
    s = client.get("/api/settings").json()
    assert s["company"]["name"] == "Nimbus Retail Pvt Ltd" and s["company"]["state"] == "Telangana (36)"
    assert s["tolerance_pct"] == 2 and s["tolerance_cap_display"] == "₹5,000" and s["vendor_auto_send"] is True

    r = client.patch("/api/settings", json={"tolerance_pct": 1.5, "tolerance_cap": 2500, "vendor_auto_send": False})
    assert r.status_code == 200, r.text
    assert r.json()["tolerance_pct"] == 1.5 and r.json()["tolerance_cap_paise"] == 250000
    assert r.json()["vendor_auto_send"] is False
    with SessionLocal() as db:
        c = db.scalar(select(CompanySettings))
        assert c.tolerance_pct == 0.015 and c.tolerance_abs_paise == 250000

    bad = client.patch("/api/settings", json={"tolerance_pct": 50, "tolerance_cap": -1})
    assert bad.status_code == 422 and set(bad.json()["errors"]) == {"tolerance_pct", "tolerance_cap"}
    assert client.get("/api/settings").json()["tolerance_pct"] == 1.5  # nothing half-applied
    # Company details are read-only: unknown fields are ignored.
    client.patch("/api/settings", json={"name": "Someone Else Ltd"})
    assert client.get("/api/settings").json()["company"]["name"] == "Nimbus Retail Pvt Ltd"


def test_vendor_auto_send_off_keeps_vendor_emails_drafted(client, emails):
    client.patch("/api/settings", json={"vendor_auto_send": False})
    run_id = client.post("/api/runs", json={"sample_name": "04_edge_split_overbill_acme.pdf"}).json()["run_id"]
    with SessionLocal() as s:
        (vendor,) = s.scalars(select(Alert).where(Alert.run_id == run_id)).all()
    assert vendor.audience == "Vendor" and vendor.status == "Drafted" and emails == []


def overbilled_conference_tables() -> dict:
    """PO-2026-110 is 2 tables at ₹35,000 (₹82,600). Billed at ₹35,550 each: ₹83,898, ₹1,298 over."""
    return {
        "vendor_name": "Deccan Office Interiors", "vendor_gstin": "36AAKFD3456Q1ZT",
        "invoice_number": "DOI/2026-27/0163", "invoice_date": "2026-09-21", "po_reference": "PO-2026-110",
        "currency": "INR",
        "lines": [{"description": "Conference table 8-seater", "qty": 2, "unit": "pcs", "unit_price": 35550,
                   "tax_rate": 18, "amount": 71100}],
        "subtotal": 71100, "cgst": 6399, "sgst": 6399, "igst": None, "total": 83898, "tax_inclusive": False,
        "bank_account": "61234567890123", "ifsc": "ICIC0001122", "payment_terms_days": 30,
        "confidence": {},
    }


def test_tolerance_change_affects_the_next_run(client, db):
    before = run_rules(db, overbilled_conference_tables())  # untouched seed: 2%, capped at ₹5,000 → ₹1,652
    assert before.decision == "Approve" and "6.2" in before.codes()

    client.patch("/api/settings", json={"tolerance_cap": 1000})
    with SessionLocal() as s:
        after = run_rules(s, overbilled_conference_tables())
    assert after.decision == "Hold"
    over = next(f for f in after.findings if f.code == "6.3")
    assert "₹1,000" in over.message
