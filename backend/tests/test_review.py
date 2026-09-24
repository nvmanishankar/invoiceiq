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

def preview(client, run_id: str, **body):
    if body:
        return client.post(f"/api/runs/{run_id}/vendor-email-preview", json=body)
    return client.get(f"/api/runs/{run_id}/vendor-email-preview")


def send(client, run_id: str, role: str | None = None, **overrides):
    """Send the drafted email as the preview shows it, with any field overridden."""
    draft = preview(client, run_id).json()
    body = {"action": "send_to_vendor", "reasons": draft["selected"], "note": draft["note"],
            "subject": draft["subject"], "body": draft["body"], **overrides}
    return review(client, run_id, role, **body)


def test_reason_chips_come_from_vendor_findings(client):
    p = preview(client, run(client, OVERBILL)).json()
    assert [(r["code"], r["title"]) for r in p["reasons"]] == [("6.5", "Over PO balance"),
                                                               ("6.6", "Quantity above ordered")]
    assert p["selected"] == ["6.5", "6.6"]  # all ticked by default
    assert p["reasons"][0]["messages"] == ["Only ₹1,18,000 remains on PO-2026-101; this invoice is ₹1,41,600."]

    p = preview(client, run(client, NO_DATE)).json()
    assert [r["code"] for r in p["reasons"]] == ["3.2"] and p["note"] == "Please add the invoice date."


def test_drafted_note_for_gst_split_balance_and_quantity(db):
    from app.services import vendor_email

    row = Invoice(run_id="RUN-NOTE", po_id="PO-2026-101")
    findings = [
        {"code": "8.3", "severity": "hold", "message": "IGST applies.", "audience": ["Vendor"],
         "evidence": {"expected_split": "IGST", "actual_split": "CGST+SGST", "rates": [18.0]}},
        {"code": "6.5", "severity": "hold", "message": "Only a little remains.", "audience": ["Vendor"],
         "evidence": {"po_id": "PO-2026-101", "remaining_paise": 11800000}},
        {"code": "6.6", "severity": "hold", "message": "Too many reams.", "audience": ["Vendor"],
         "evidence": {"invoice_line": "A4 paper", "po_line": "A4 copier paper", "po_line_no": 1,
                      "already": 1500, "this_invoice": 600, "ordered": 2000}},
    ]
    chips = vendor_email.reason_chips(db, row, findings)
    assert [c["title"] for c in chips] == ["Wrong GST split", "Over PO balance", "Quantity above ordered"]
    assert vendor_email.draft_note(chips, ["8.3", "6.5", "6.6"]).splitlines() == [
        "Please reissue with IGST at 18% instead of CGST + SGST.",
        "Only ₹1,18,000 remains on PO-2026-101; please bill no more than that.",
        "Only 500 reams of A4 copier paper remain on PO-2026-101; please bill no more than that.",
    ]
    assert vendor_email.draft_note(chips, ["6.5"]) == "Only ₹1,18,000 remains on PO-2026-101; please bill no more than that."


def test_drafted_note_for_the_wrong_split_sample(client):
    p = preview(client, run(client, "08_extra_wrong_split_brighttech.pdf")).json()
    assert p["note"] == "Please reissue with IGST at 18% instead of CGST + SGST."


def test_preview_follows_the_chosen_reasons_and_sends_nothing(client, emails):
    run_id = run(client, OVERBILL)
    emails.clear()
    full = preview(client, run_id).json()
    assert full["subject"] == "[InvoiceIQ → Vendor: Acme Supplies] Invoice ACME/2026/0417 needs a correction"
    assert "Only ₹1,18,000 remains on PO-2026-101; this invoice is ₹1,41,600." in full["body"]
    assert "Only 500 reams of A4 copier paper" in full["body"]  # the drafted note, from 6.6's evidence

    one = preview(client, run_id, reasons=["6.5"]).json()
    assert one["selected"] == ["6.5"] and "2,100 invoiced in total" not in one["body"]
    assert one["note"] == one["drafted_note"] == "Only ₹1,18,000 remains on PO-2026-101; please bill no more than that."

    mine = preview(client, run_id, reasons=["6.5", "other"], note="Split it into two invoices, please.").json()
    assert "  Split it into two invoices, please." in mine["body"] and mine["note"] != mine["drafted_note"]

    assert preview(client, run_id, reasons=[]).status_code == 422  # at least one reason
    assert preview(client, run_id, reasons=["other"], note=" ").status_code == 422  # Other needs a note
    assert preview(client, run_id, reasons=["4.7"]).status_code == 422  # not a vendor reason on this run
    assert emails == [] and detail(client, run_id)["status"] == "needs_review"
    assert preview(client, run(client, HAPPY)).status_code == 409  # nothing to send on an approved run


def test_send_to_vendor_sends_the_edited_email(client, emails):
    run_id = run(client, OVERBILL)
    emails.clear()
    draft = preview(client, run_id).json()
    subject = "Invoice ACME/2026/0417: please split it"
    body = draft["body"].replace("Please reply with a corrected invoice.", "Please send two invoices instead.")
    r = review(client, run_id, "AP clerk", action="send_to_vendor", reasons=["6.5", "6.6"], note=draft["note"],
               subject=f"  {subject} ", body=body)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "waiting_on_vendor"

    assert emails == [{"subject": subject, "body": body.strip()}]  # exactly what the reviewer left
    d = detail(client, run_id)
    assert d["status"] == "waiting_on_vendor" and d["decision"]["decision"] == "Hold"
    alert = [a for a in d["alerts"] if a["audience"] == "Vendor"][-1]  # after the run's own auto-sent one
    assert alert["subject"] == subject and alert["status"] == "Sent" and alert["intended_for"].endswith("(accounts)")
    rev = d["reviews"][0]
    assert rev["action"] == "send_to_vendor" and rev["reason"] == "Over PO balance, Quantity above ordered"
    email = rev["field_changes"]["email"]
    assert email["subject"] == subject and email["body"] == body.strip() and email["reasons"] == ["6.5", "6.6"]
    assert email["email_edited"] is True and email["note_edited"] is False
    assert rev["field_changes"]["status"]["after"] == "waiting_on_vendor"
    assert client.get("/api/review-queue").json()["count"] == 0


def test_send_to_vendor_records_an_unedited_draft(client, emails):
    run_id = run(client, NO_DATE)
    emails.clear()
    assert send(client, run_id).status_code == 200
    email = detail(client, run_id)["reviews"][0]["field_changes"]["email"]
    assert email["email_edited"] is False and email["note_edited"] is False
    assert emails[0]["body"] == email["body"] and "Please add the invoice date." in email["body"]


def test_send_to_vendor_records_an_edited_note(client):
    run_id = run(client, NO_DATE)
    note = "Please add the invoice date; we can't pay an undated invoice."
    draft = preview(client, run_id, reasons=["3.2"], note=note).json()
    assert send(client, run_id, note=note, subject=draft["subject"], body=draft["body"]).status_code == 200
    email = detail(client, run_id)["reviews"][0]["field_changes"]["email"]
    assert email["note_edited"] is True and email["email_edited"] is False and email["note"] == note


@pytest.mark.parametrize("overrides, why", [
    ({"subject": "  "}, "subject"),
    ({"body": ""}, "body"),
    ({"subject": "x" * 201}, "subject is longer"),
    ({"body": "x" * 10_001}, "longer than"),
    ({"reasons": []}, "at least one reason"),
    ({"reasons": None}, "at least one reason"),
    ({"reasons": ["other"], "note": ""}, "add a note"),
    ({"reasons": ["Unreadable scan"]}, "aren't on this invoice"),
])
def test_send_to_vendor_validates(client, emails, overrides, why):
    run_id = run(client, OVERBILL)
    emails.clear()
    r = send(client, run_id, **overrides)
    assert r.status_code == 422 and why in r.json()["detail"]
    assert emails == [] and detail(client, run_id)["status"] == "needs_review"


def test_send_to_vendor_with_other_and_a_note(client, emails):
    run_id = run(client, OVERBILL)
    emails.clear()
    draft = preview(client, run_id, reasons=["other"], note="Wrong billing address.").json()
    r = send(client, run_id, reasons=["other"], note="Wrong billing address.", subject=draft["subject"],
             body=draft["body"])
    assert r.status_code == 200, r.text
    assert detail(client, run_id)["reviews"][0]["reason"] == "Other"
    assert "Wrong billing address." in emails[0]["body"] and "remains on PO-2026-101" not in emails[0]["body"]


def test_send_to_vendor_refused_on_fraud(client, emails):
    run_id = run(client, FRAUD)
    emails.clear()
    assert preview(client, run_id).status_code == 409
    r = review(client, run_id, "Finance", action="send_to_vendor", reasons=["other"], note="x",
               subject="Please call us", body="Your bank details changed.")
    assert r.status_code == 409 and "fraud" in r.json()["detail"]
    assert emails == [] and detail(client, run_id)["status"] == "needs_review"


def test_send_to_vendor_replaces_an_unsent_draft(client, emails, monkeypatch):
    monkeypatch.setattr(settings, "VENDOR_AUTO_SEND", False)
    run_id = run(client, OVERBILL)
    assert [a["status"] for a in detail(client, run_id)["alerts"]] == ["Drafted"]
    send(client, run_id)
    assert [a["status"] for a in detail(client, run_id)["alerts"]] == ["Sent"]


# --- Corrected invoice ----------------------------------------------------------------------------------------------

def upload_corrected(client, run_id: str, name: str, role: str | None = None):
    headers = {"X-Role": role} if role else {}
    return client.post(f"/api/runs/{run_id}/corrected", json={"sample_name": name}, headers=headers)


def test_corrected_upload_supersedes_the_original(client):
    original = run(client, OVERBILL)
    assert send(client, original).status_code == 200
    assert detail(client, original)["status"] == "waiting_on_vendor"

    # The vendor sends the same PDF back: the worst case for the duplicate check.
    r = upload_corrected(client, original, OVERBILL, "AP clerk")
    assert r.status_code == 202, r.text
    new = r.json()["run_id"]
    assert new != original and r.json()["replaces"] == original

    old = detail(client, original)
    assert old["status"] == "superseded" and old["decision"]["decision"] == "Hold"  # decision unchanged
    assert old["replaced_by"] == new and old["parent_upload_id"] is None
    last = old["reviews"][-1]
    assert last["action"] == "upload_corrected" and last["reviewer"] == "AP clerk" and new in last["reason"]
    assert last["field_changes"]["status"] == {"label": "Status", "before": "waiting_on_vendor", "after": "superseded"}

    events = read_stream(client, new)
    assert [d["order"] for k, d in events if k == "stage"] == list(range(1, 11))  # checked fully, from stage 1
    fresh = detail(client, new)
    assert fresh["parent_upload_id"] == original and fresh["replaced_by"] is None
    assert {"6.5", "6.6"} <= codes(fresh)
    assert not codes(fresh) & {"7.1", "7.2", "7.3", "7.4"}  # not a duplicate of the run it replaces
    assert fresh["status"] == "needs_review"

    queue = [q["run_id"] for q in client.get("/api/review-queue").json()["runs"]]
    assert queue == [new]
    assert [r["status"] for r in client.get("/api/runs", params={"status": "superseded"}).json()] == ["superseded"]
    kpis = client.get("/api/stats").json()["kpis"]
    assert kpis["open_review"] == 1 and kpis["waiting_on_vendor"] == 0

    # A superseded run is closed: no second replacement, no review.
    assert upload_corrected(client, original, OVERBILL).status_code == 409
    assert review(client, original, action="reject", reason="x").status_code == 409

    # The same file sent again as a new upload (not a correction) is still caught, against the live replacement.
    again = detail(client, run(client, OVERBILL))
    assert "7.1" in codes(again) and any(new in f["message"] for f in again["findings"] if f["code"] == "7.1")


def test_corrected_upload_from_the_review_queue(client):
    original = run(client, NO_DATE)
    r = upload_corrected(client, original, HAPPY)
    assert r.status_code == 202, r.text
    read_stream(client, r.json()["run_id"])
    assert detail(client, original)["status"] == "superseded"
    assert detail(client, r.json()["run_id"])["decision"]["decision"] == "Approve"


def test_corrected_upload_guards(client):
    approved = run(client, HAPPY)
    assert upload_corrected(client, approved, HAPPY).status_code == 409
    assert upload_corrected(client, "RUN-NOPE", HAPPY).status_code == 404
    fraud = run(client, FRAUD)
    r = upload_corrected(client, fraud, FRAUD, "AP clerk")
    assert r.status_code == 403 and "Only Finance" in r.json()["detail"]
    assert detail(client, fraud)["status"] == "needs_review"
    with SessionLocal() as db:  # the refused upload left nothing behind
        assert db.query(Invoice).filter(Invoice.parent_upload_id == fraud).count() == 0


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
