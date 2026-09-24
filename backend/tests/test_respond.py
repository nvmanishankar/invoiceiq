"""The vendor response link, reply-to and reminders (build guide section 10, 'Vendor response link')."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app import alerts
from app.config import settings
from app.db import SessionLocal
from app.models import Alert, Invoice, RunStage, utcnow
from app.services import runs as run_service
from tests.helpers import SAMPLES
from tests.test_alerts import REAL_SEND
from tests.test_review import FRAUD, OVERBILL, client, detail, read_stream, review, run, send  # noqa: F401

QUOTATION = "07_extra_quotation_acme.pdf"  # Reject: 1.4 (Vendor)
PDF = (SAMPLES / OVERBILL).read_bytes()
SAFE_KEYS = {"company_name", "vendor_name", "invoice_no", "invoice_date", "total_display", "po_id", "issues",
             "expires_on", "message_max"}


def vendor_alerts(run_id: str) -> list[Alert]:
    with SessionLocal() as db:
        return list(db.scalars(select(Alert).where(Alert.run_id == run_id, Alert.audience == "Vendor")
                               .order_by(Alert.alert_id)))


def token_of(run_id: str) -> str:
    return vendor_alerts(run_id)[-1].response_token


def waiting(client) -> tuple[str, str]:
    """Sample 04 sent back to the vendor by a reviewer: (run id, the live token)."""
    run_id = run(client, OVERBILL)
    assert send(client, run_id, "AP clerk").status_code == 200
    return run_id, token_of(run_id)


def respond(client, token: str, data: bytes = PDF, message: str | None = None, name: str = "corrected.pdf"):
    form = {"message": message} if message is not None else {}
    return client.post(f"/api/respond/{token}", files={"file": (name, data, "application/pdf")}, data=form)


# --- Tokens ---------------------------------------------------------------------------------------------------------

def test_hold_vendor_emails_get_a_token_and_a_new_email_replaces_it(client, emails):
    run_id = run(client, OVERBILL)
    (auto,) = vendor_alerts(run_id)
    assert auto.status == "Sent" and len(auto.response_token) >= 40
    assert auto.token_expires - auto.sent_at > timedelta(days=6, hours=23)
    expiry = f"{auto.token_expires:%d %b %Y}"
    assert (f"Upload your corrected invoice here (link valid until {expiry}): "
            f"{settings.BASE_URL}/respond/{auto.response_token}. You can also reply to this email with the PDF "
            "attached.") in auto.body
    assert client.get(f"/api/respond/{auto.response_token}").status_code == 200

    send(client, run_id)
    first, second = vendor_alerts(run_id)
    assert second.response_token and second.response_token != first.response_token
    assert second.response_token in emails[-1]["body"] and emails[-1]["subject"].endswith(f"Ref {run_id}")
    r = client.get(f"/api/respond/{first.response_token}")  # one active link per run
    assert r.status_code == 410 and r.json()["state"] == "replaced"
    assert client.get(f"/api/respond/{second.response_token}").status_code == 200


def test_no_token_on_fraud_or_reject(client, emails):
    fraud = run(client, FRAUD)
    assert vendor_alerts(fraud) == []
    with SessionLocal() as db:
        assert db.scalar(select(Alert).where(Alert.run_id == fraud, Alert.response_token.is_not(None))) is None
    assert not any("/respond/" in e["body"] for e in emails)

    rejected = run(client, QUOTATION)
    (vendor,) = vendor_alerts(rejected)
    assert vendor.response_token is None and vendor.token_expires is None
    assert "/respond/" not in vendor.body and "Please don't resend this document." in vendor.body


def test_drafted_vendor_email_gets_a_fresh_link_when_sent_from_the_outbox(client, emails, monkeypatch):
    monkeypatch.setattr(settings, "VENDOR_AUTO_SEND", False)
    run_id = run(client, OVERBILL)
    (drafted,) = vendor_alerts(run_id)
    assert drafted.status == "Drafted" and drafted.response_token
    assert client.post(f"/api/alerts/{drafted.alert_id}/send").status_code == 200
    (sent,) = vendor_alerts(run_id)
    assert sent.response_token != drafted.response_token and sent.response_token in emails[-1]["body"]
    assert drafted.response_token not in emails[-1]["body"]


# --- GET ------------------------------------------------------------------------------------------------------------

def test_get_returns_only_vendor_safe_fields(client):
    run_id, token = waiting(client)
    r = client.get(f"/api/respond/{token}")
    assert r.status_code == 200, r.text
    page = r.json()
    assert set(page) == SAFE_KEYS
    assert page["company_name"] == "Nimbus Retail Pvt Ltd"
    assert page["vendor_name"] == "Acme Supplies Private Limited"
    assert page["invoice_no"] == "ACME/2026/0417" and page["total_display"] == "₹1,41,600"
    assert page["po_id"] == "PO-2026-101" and page["invoice_date"]
    assert f"(link valid until {page['expires_on']})" in vendor_alerts(run_id)[-1].body  # same date as the email
    d = detail(client, run_id)
    vendor_msgs = {f["message"] for f in d["findings"] if "Vendor" in f["audience"] and f["severity"] == "hold"}
    assert set(page["issues"]) == vendor_msgs and len(page["issues"]) == 2
    text = r.text
    assert run_id not in text and "RUN-" not in text  # no run internals
    for secret in filter(None, (d["invoice"]["bank_account"], (d.get("vendor") or {}).get("bank_account_on_file"))):
        assert secret not in text
    assert "evidence" not in text and "severity" not in text


def test_unknown_expired_used_and_closed_links(client):
    assert client.get("/api/respond/not-a-real-token").status_code == 404

    run_id, token = waiting(client)
    with SessionLocal() as db:
        alert = db.scalar(select(Alert).where(Alert.response_token == token))
        alert.token_expires = utcnow() - timedelta(minutes=1)
        db.commit()
    r = client.get(f"/api/respond/{token}")
    assert r.status_code == 410 and r.json()["state"] == "expired"
    assert respond(client, token).status_code == 410

    run_id, token = waiting(client)
    assert review(client, run_id, action="reject", reason="Vendor withdrew it").status_code == 200
    r = client.get(f"/api/respond/{token}")
    assert r.status_code == 410 and r.json()["state"] == "closed"

    run_id, token = waiting(client)
    assert respond(client, token).status_code == 202
    for r in (client.get(f"/api/respond/{token}"), respond(client, token)):
        assert r.status_code == 410 and r.json()["state"] == "used"


def test_link_closes_if_a_rerun_finds_fraud(client):
    run_id, token = waiting(client)
    with SessionLocal() as db:
        stage = db.scalar(select(RunStage).where(RunStage.run_id == run_id, RunStage.stage_order == 4))
        stage.details = {**stage.details, "findings": [{"code": "4.7", "severity": "hold", "fraud": True,
                                                        "message": "Bank changed", "audience": ["Finance"]}]}
        db.commit()
    r = client.get(f"/api/respond/{token}")
    assert r.status_code == 410 and r.json()["state"] == "closed"


# --- POST -----------------------------------------------------------------------------------------------------------

def test_post_starts_a_linked_corrected_run(client, emails):
    original, token = waiting(client)
    emails.clear()
    r = respond(client, token, message="  Split into two invoices as asked.  ", name="../../acme corrected.pdf")
    assert r.status_code == 202, r.text
    assert r.json() == {"message": "Received, we're checking it"}  # never the decision

    old = detail(client, original)
    new = old["replaced_by"]
    assert new and old["status"] == "superseded" and old["decision"]["decision"] == "Hold"
    responded = next(x for x in old["reviews"] if x["action"] == "vendor_response")
    assert responded["reason"] == "Vendor responded via link. Their message: Split into two invoices as asked."
    assert responded["reviewer"] == "Vendor (response link)"
    assert old["reviews"][-1]["action"] == "upload_corrected"

    read_stream(client, new)
    fresh = detail(client, new)
    assert fresh["parent_upload_id"] == original and fresh["file_name"] == "acme corrected.pdf"
    assert fresh["status"] == "needs_review"

    with SessionLocal() as db:
        used = db.scalar(select(Alert).where(Alert.response_token == token))
        assert used.token_used_at is not None
        ap = db.scalars(select(Alert).where(Alert.run_id == original, Alert.audience == "AP")).all()
    (ap,) = ap
    assert ap.status == "Sent" and ap.intended_for == "Nimbus Retail AP team"
    assert "Vendor sent a corrected invoice for ACME/2026/0417" in ap.subject
    assert f"/process?run={new}" in ap.body and "Split into two invoices as asked." in ap.body
    assert emails[0]["subject"] == ap.subject


def test_used_link_says_used_even_when_emails_are_off(client, monkeypatch):
    monkeypatch.setattr(settings, "SEND_EMAILS", False)  # the vendor email stays Drafted
    original, token = waiting(client)
    assert vendor_alerts(original)[-1].status == "Drafted"
    assert respond(client, token).status_code == 202
    r = client.get(f"/api/respond/{token}")
    assert r.status_code == 410 and r.json()["state"] == "used"


def test_post_validates_the_upload(client, emails):
    _, token = waiting(client)
    r = respond(client, token, message="x" * 1_001)
    assert r.status_code == 422 and "1,000" in r.json()["detail"]
    assert respond(client, token, data=b"GIF89a not a pdf", name="scan.gif").status_code == 415
    assert respond(client, token, data=b"").status_code == 400
    assert client.post(f"/api/respond/{token}", json={"file": "x"}).status_code == 415
    assert client.get(f"/api/respond/{token}").status_code == 200  # nothing was used up


def test_post_respects_the_daily_cap(client, monkeypatch):
    original, token = waiting(client)
    with SessionLocal() as db:
        monkeypatch.setattr(settings, "MAX_RUNS_PER_DAY", run_service.runs_today(db))
    r = respond(client, token)
    assert r.status_code == 429 and r.json()["state"] == "busy"
    assert detail(client, original)["status"] == "waiting_on_vendor"
    assert client.get(f"/api/respond/{token}").status_code == 200  # still usable tomorrow


# --- Reminders and waiting time -------------------------------------------------------------------------------------

def test_reminder_refreshes_the_token(client, emails):
    run_id, old_token = waiting(client)
    emails.clear()
    r = review(client, run_id, "AP clerk", action="send_reminder")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "waiting_on_vendor"

    last = vendor_alerts(run_id)[-1]
    assert last.subject.startswith("Reminder: [InvoiceIQ → Vendor: Acme Supplies]")
    assert last.subject.endswith(f"Ref {run_id}")
    assert last.response_token != old_token and f"/respond/{last.response_token}." in last.body
    assert emails == [{"subject": last.subject, "body": last.body}]
    assert client.get(f"/api/respond/{old_token}").status_code == 410
    assert client.get(f"/api/respond/{last.response_token}").status_code == 200

    review(client, run_id, action="send_reminder")  # a second reminder doesn't stack the prefix
    assert vendor_alerts(run_id)[-1].subject.count("Reminder:") == 1
    d = detail(client, run_id)
    assert [x["action"] for x in d["reviews"]][-2:] == ["send_reminder", "send_reminder"]


def test_reminder_guards(client, emails):
    held = run(client, OVERBILL)
    r = review(client, held, action="send_reminder")
    assert r.status_code == 409 and "waiting on the vendor" in r.json()["detail"]

    fraud = run(client, FRAUD)
    with SessionLocal() as db:  # a fraud run parked on the vendor should never happen; the reminder still refuses
        db.get(Invoice, fraud).status = "waiting_on_vendor"
        db.commit()
    emails.clear()
    r = review(client, fraud, "Finance", action="send_reminder")
    assert r.status_code == 409 and "fraud" in r.json()["detail"] and emails == []


def test_queue_and_detail_show_how_long_the_vendor_has_had_it(client):
    run_id, _ = waiting(client)
    q = client.get("/api/review-queue").json()
    assert q["count"] == 0 and [w["run_id"] for w in q["waiting"]] == [run_id]
    since = q["waiting"][0]["waiting_since"]
    assert since and detail(client, run_id)["waiting_since"] == since
    assert detail(client, run(client, OVERBILL))["waiting_since"] is None


# --- Reply-To -------------------------------------------------------------------------------------------------------

def test_every_email_replies_to_the_owner(db, monkeypatch):
    from tests.helpers import run_sample

    calls = []
    monkeypatch.setattr(alerts, "_send_email", REAL_SEND)
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(settings, "OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(alerts.resend.Emails, "send", lambda params: calls.append(params) or {"id": "x"})
    run_sample(db, OVERBILL)
    run_sample(db, FRAUD)
    assert len(calls) == 3
    assert all(c["reply_to"] == "owner@example.com" and c["to"] == ["owner@example.com"] for c in calls)


@pytest.mark.parametrize("body", [
    "Hello\n\nThank you,\nAP",
    "Hello",
])
def test_link_is_added_if_a_reviewer_deleted_it(body):
    url, expires = alerts.respond_url("tok"), utcnow()
    out = alerts.with_response_link(body, url, expires)
    assert out.count("/respond/tok.") == 1
    if "Thank you," in body:
        assert out.index("/respond/tok") < out.index("Thank you,")
