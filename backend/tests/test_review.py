"""Human review: POST /api/runs/{id}/review, the review queue, resume via SSE (build guide section 11)."""

import json

import pytest
from fastapi.testclient import TestClient

from app import llm, seed
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Invoice, InvoiceLine, Review, clip
from app.pipeline.s2_extract import write_invoice_row
from app.schemas import ExtractedInvoice
from app.services import runs as run_service
from tests.helpers import TODAY

OVERBILL = "04_edge_split_overbill_acme.pdf"  # Hold: 6.5, 6.6 (Vendor)
FRAUD = "06_edge_bank_changed_brighttech.pdf"  # Hold: 4.7 (Finance, AP)
NO_DATE = "09_extra_missing_date_deccan.pdf"  # Hold: 3.2 (Vendor)
HAPPY = "01_happy_deccan.pdf"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "MIN_STAGE_MS", 0)
    monkeypatch.setattr(run_service, "today", lambda: TODAY)
    seed.reset()
    with TestClient(app) as c:
        yield c


def read_stream(client, run_id: str) -> list[tuple[str, dict]]:
    events, event = [], None
    with client.stream("GET", f"/api/runs/{run_id}/stream") as r:
        for line in r.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                events.append((event, json.loads(line[6:])))
    return events


def run(client, name: str) -> str:
    r = client.post("/api/runs", json={"sample_name": name})
    assert r.status_code == 202, r.text
    run_id = r.json()["run_id"]
    read_stream(client, run_id)
    return run_id


def review(client, run_id: str, role: str | None = None, **body):
    headers = {"X-Role": role} if role else {}
    return client.post(f"/api/runs/{run_id}/review", json=body, headers=headers)


def detail(client, run_id: str) -> dict:
    return client.get(f"/api/runs/{run_id}").json()


def codes(d: dict) -> set[str]:
    return {f["code"] for f in d["findings"]}


# --- Queue ----------------------------------------------------------------------------------------------------------

def test_review_queue_lists_held_runs(client):
    held = run(client, OVERBILL)
    fraud = run(client, FRAUD)
    run(client, HAPPY)

    q = client.get("/api/review-queue").json()
    assert q["count"] == 2
    assert [r["run_id"] for r in q["runs"]] == [held, fraud]  # oldest first
    assert all(r["status"] == "needs_review" and r["decision"] == "Hold" for r in q["runs"])

    review(client, held, reason="Duplicate of a paper invoice", action="reject")
    assert client.get("/api/review-queue").json()["count"] == 1


# --- Confirm --------------------------------------------------------------------------------------------------------

def test_confirm_with_correction_resumes_from_stage_3(client, emails):
    run_id = run(client, NO_DATE)
    before = detail(client, run_id)
    assert before["decision"]["decision"] == "Hold" and "3.2" in codes(before)
    stage2_at = before["stages"][1]["created_at"]

    r = review(client, run_id, "AP clerk", action="confirm", fields={"invoice_date": "2026-09-19"})
    assert r.status_code == 200, r.text
    assert r.json() == {"run_id": run_id, "action": "confirm", "status": "running", "resumed": True}

    events = read_stream(client, run_id)  # resumed runs stream through the same endpoint
    stages = [d for k, d in events if k == "stage"]
    assert [s["order"] for s in stages] == list(range(1, 11))
    assert stages[1]["created_at"] == stage2_at  # stages 1-2 kept, 3 onwards ran again
    assert events[-2] == ("decision", events[-2][1]) and events[-2][1]["decision"] == "Approve"

    after = detail(client, run_id)
    assert after["status"] == "approved" and after["invoice"]["invoice_date"] == "2026-09-19"
    assert "3.2" not in codes(after)
    (rev,) = after["reviews"]
    assert rev["action"] == "confirm" and rev["reviewer"] == "AP clerk"
    assert rev["field_changes"]["invoice_date"]["before"] is None
    assert rev["field_changes"]["invoice_date"]["after"] == "2026-09-19"


def test_confirm_clears_low_confidence_hold(client, monkeypatch):
    real = llm.extract

    def low_total(*a, **k):
        ex = real(*a, **k).model_copy(deep=True)
        ex.invoices[0].confidence.total = "low"
        return ex

    monkeypatch.setattr(llm, "extract", low_total)
    run_id = run(client, HAPPY)
    held = detail(client, run_id)
    assert held["decision"]["decision"] == "Hold" and "2.2" in codes(held)

    assert review(client, run_id, action="confirm", fields={}).status_code == 200
    after = detail(client, run_id)
    assert after["decision"]["decision"] == "Approve"
    assert "2.2" not in codes(after)
    assert after["extraction"]["confidence"]["total"] == "high"
    assert "confirmed by AP clerk" in after["stages"][1]["message"]
    assert after["reviews"][0]["field_changes"] is None


def test_confirm_rejects_bad_values_and_unknown_fields(client):
    run_id = run(client, NO_DATE)
    r = review(client, run_id, action="confirm", fields={"invoice_date": "19/09/2026"})
    assert r.status_code == 422 and "YYYY-MM-DD" in r.json()["detail"]
    assert review(client, run_id, action="confirm", fields={"total": "lots"}).status_code == 422
    assert review(client, run_id, action="confirm", fields={"decision": "Approve"}).status_code == 422
    assert detail(client, run_id)["status"] == "needs_review"  # nothing changed


def test_confirm_truncates_long_strings(client):
    run_id = run(client, NO_DATE)
    r = review(client, run_id, action="confirm",
               fields={"invoice_date": "2026-09-19", "invoice_number": "X" * 500, "bank_account": "9" * 200})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        row = db.get(Invoice, run_id)
        assert len(row.invoice_no) == 100 and len(row.invoice_no_norm) <= 100 and len(row.bank_account) == 40


def test_write_invoice_row_cuts_every_string_to_its_column():
    inv = ExtractedInvoice(invoice_number="N" * 300, vendor_gstin="G" * 80, bank_account="1" * 90,
                           lines=[{"description": "d" * 5000, "unit": "U" * 50, "qty": 1}])
    row = Invoice(run_id="RUN-T")
    write_invoice_row(row, "i" * 60, inv.model_dump(mode="json"), inv)
    for col in ("doc_type", "invoice_no", "invoice_no_norm", "vendor_tax_id", "bank_account"):
        assert len(getattr(row, col)) == Invoice.__table__.c[col].type.length, col
    assert len(row.lines[0].unit) == 20 and len(row.lines[0].description) == 5000  # Text has no limit
    assert clip(InvoiceLine, "qty", 3.0) == 3.0


# --- Pick PO --------------------------------------------------------------------------------------------------------

def test_pick_po_resumes_from_stage_6(client):
    run_id = run(client, OVERBILL)
    before = detail(client, run_id)
    stage5_at = before["stages"][4]["created_at"]

    r = review(client, run_id, action="pick_po", po_id="po-2026-104")
    assert r.status_code == 200, r.text
    assert r.json()["resumed"]

    events = read_stream(client, run_id)
    stages = [d for k, d in events if k == "stage"]
    assert [s["order"] for s in stages] == list(range(1, 11))
    assert stages[4]["created_at"] == stage5_at and "picked by AP clerk" in stages[4]["message"]

    after = detail(client, run_id)
    assert after["po_id"] == "PO-2026-104" and after["po_match_type"] == "Explicit (reviewer)"
    assert "6.5" not in codes(after)  # the stage 6 checks now ran against PO-2026-104
    assert after["reviews"][0]["field_changes"]["po_id"] == {"label": "PO", "before": "PO-2026-101",
                                                            "after": "PO-2026-104"}


@pytest.mark.parametrize("po_id, why", [
    ("PO-2026-105", "issued to BrightTech"),  # another vendor
    ("PO-2026-999", "no PO called"),
    ("", "PO number"),
])
def test_pick_po_refuses_bad_choices(client, po_id, why):
    run_id = run(client, OVERBILL)
    r = review(client, run_id, action="pick_po", po_id=po_id)
    assert r.status_code == 422 and why in r.json()["detail"]


# --- Override -------------------------------------------------------------------------------------------------------

def test_override_approves_with_reason(client):
    run_id = run(client, OVERBILL)
    assert review(client, run_id, action="override").status_code == 422  # reason required

    r = review(client, run_id, "AP clerk", action="override", reason="Extra reams agreed by phone with procurement")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    d = detail(client, run_id)
    assert d["decision"]["decision"] == "Approve" and d["status"] == "approved"
    assert d["decision"]["headline"].startswith("Approved by AP clerk override")
    assert d["decision"]["reasons"][0]["message"] == "Approved by AP clerk: Extra reams agreed by phone with procurement"
    (rev,) = d["reviews"]
    assert rev["action"] == "override" and rev["field_changes"]["decision"] == {
        "label": "Decision", "before": "Hold", "after": "Approve"}


@pytest.mark.parametrize("role", [None, "AP clerk", "Procurement"])
def test_override_blocked_on_fraud_for_non_finance(client, role):
    run_id = run(client, FRAUD)
    r = review(client, run_id, role, action="override", reason="Looks fine")
    assert r.status_code == 403 and "Only Finance" in r.json()["detail"]
    d = detail(client, run_id)
    assert d["status"] == "needs_review" and d["reviews"] == []


def test_finance_can_override_fraud(client):
    run_id = run(client, FRAUD)
    r = review(client, run_id, "Finance", action="override", reason="Called BrightTech on file number; change confirmed")
    assert r.status_code == 200, r.text
    d = detail(client, run_id)
    assert d["status"] == "approved" and d["reviews"][0]["reviewer"] == "Finance"


# --- Send to vendor -------------------------------------------------------------------------------------------------

def test_send_to_vendor(client, emails):
    run_id = run(client, OVERBILL)
    emails.clear()
    r = review(client, run_id, action="send_to_vendor", reason="Missing information",
               note="Please split the invoice: 2,000 reams on PO-2026-101 only.")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "waiting_on_vendor"

    d = detail(client, run_id)
    assert d["status"] == "waiting_on_vendor" and d["decision"]["decision"] == "Hold"
    (email,) = emails
    assert email["subject"].startswith("[InvoiceIQ → Vendor: Acme Supplies]")
    assert "Missing information." in email["body"] and "Please split the invoice" in email["body"]
    assert "Only ₹1,18,000 remains on PO-2026-101" in email["body"]
    rev = d["reviews"][0]
    assert rev["action"] == "send_to_vendor" and rev["reason"].startswith("Missing information: Please split")
    assert rev["field_changes"]["status"]["after"] == "waiting_on_vendor"
    assert client.get("/api/review-queue").json()["count"] == 0


def test_send_to_vendor_validates_reason(client):
    run_id = run(client, OVERBILL)
    assert review(client, run_id, action="send_to_vendor", reason="Because").status_code == 422
    assert review(client, run_id, action="send_to_vendor", reason="Other").status_code == 422  # note required
    assert review(client, run_id, action="send_to_vendor", reason="Other", note="Wrong address").status_code == 200


def test_send_to_vendor_refused_on_fraud(client, emails):
    run_id = run(client, FRAUD)
    emails.clear()
    r = review(client, run_id, "Finance", action="send_to_vendor", reason="Missing information", note="x")
    assert r.status_code == 409 and "fraud" in r.json()["detail"]
    assert emails == [] and detail(client, run_id)["status"] == "needs_review"


def test_send_to_vendor_replaces_an_unsent_draft(client, emails, monkeypatch):
    monkeypatch.setattr(settings, "VENDOR_AUTO_SEND", False)
    run_id = run(client, OVERBILL)
    assert [a["status"] for a in detail(client, run_id)["alerts"]] == ["Drafted"]
    review(client, run_id, action="send_to_vendor", reason="Unreadable scan")
    assert [a["status"] for a in detail(client, run_id)["alerts"]] == ["Sent"]


# --- Reject ---------------------------------------------------------------------------------------------------------

def test_reject(client):
    run_id = run(client, FRAUD)
    assert review(client, run_id, action="reject", reason="  ").status_code == 422
    r = review(client, run_id, "AP clerk", action="reject", reason="Vendor confirmed they didn't send it")
    assert r.status_code == 200, r.text
    d = detail(client, run_id)
    assert d["decision"]["decision"] == "Reject" and d["status"] == "rejected"
    assert d["decision"]["headline"] == "Rejected by AP clerk: Vendor confirmed they didn't send it"
    assert d["reviews"][0]["action"] == "reject"


# --- Guards ---------------------------------------------------------------------------------------------------------

def test_only_held_runs_can_be_reviewed(client):
    run_id = run(client, HAPPY)
    r = review(client, run_id, action="reject", reason="x")
    assert r.status_code == 409 and "approved" in r.json()["detail"]
    assert review(client, "RUN-NOPE", action="reject", reason="x").status_code == 404
    assert review(client, run_id, action="approve").status_code == 422


def test_closed_run_cannot_be_reviewed_twice(client):
    run_id = run(client, OVERBILL)
    assert review(client, run_id, action="reject", reason="x").status_code == 200
    assert review(client, run_id, action="override", reason="y").status_code == 409
    with SessionLocal() as db:
        assert db.query(Review).filter(Review.run_id == run_id).count() == 1
