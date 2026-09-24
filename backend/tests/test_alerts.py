"""Alerts: grouping, fraud suppression, vendor auto-send, Resend failures, Outbox (build guide section 10)."""

from collections import Counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import alerts, seed
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Alert, Invoice
from app.services import runs as run_service
from tests.helpers import TODAY, run_sample

REAL_SEND = alerts._send_email  # captured before the conftest recorder replaces it


def run_alerts(db, run_id: str) -> list[Alert]:
    return list(db.scalars(select(Alert).where(Alert.run_id == run_id).order_by(Alert.alert_id)))


def test_one_alert_per_audience_listing_every_finding(db, emails):
    ctx = run_sample(db, "04_edge_split_overbill_acme.pdf")
    rows = run_alerts(db, ctx.run_id)

    assert Counter(a.audience for a in rows) == {"Vendor": 1}
    vendor = rows[0]
    for code in ("6.5", "6.6"):
        assert next(f for f in ctx.findings if f.code == code).message in vendor.body
    assert vendor.subject.startswith("[InvoiceIQ → Vendor: Acme Supplies]")
    assert vendor.intended_for == "Acme Supplies Private Limited (accounts)"
    assert vendor.body.startswith("Intended for: Acme Supplies Private Limited (accounts)")
    assert vendor.to_email == settings.OWNER_EMAIL
    assert vendor.status == "Sent" and vendor.sent_at is not None
    assert vendor.response_token and f"/respond/{vendor.response_token}" in vendor.body
    assert [e["subject"] for e in emails] == [vendor.subject]


def test_fraud_never_emails_the_vendor(db, emails):
    ctx = run_sample(db, "06_edge_bank_changed_brighttech.pdf")
    rows = run_alerts(db, ctx.run_id)

    assert {a.audience for a in rows} == {"Finance", "AP"}
    finance = next(a for a in rows if a.audience == "Finance")
    assert finance.subject.startswith("[InvoiceIQ → Finance · Fraud check]")
    assert finance.intended_for == "Nimbus Retail Finance"
    assert "…7766" in finance.body and "…5667" in finance.body
    assert "Do not reply to the email that sent this invoice" in finance.body
    assert f"/review/{ctx.run_id}" in finance.body
    assert not any("Vendor" in e["subject"] for e in emails)


def test_fraud_suppresses_vendor_even_when_vendor_findings_exist(db):
    ctx = run_sample(db, "06_edge_bank_changed_brighttech.pdf")
    ctx.add("6.5", "hold", "Over the PO.", ["Vendor"])
    built = alerts.build_alerts(ctx, "Hold", {"Vendor": [ctx.findings[-1]], "AP": ctx.findings[:1]}, "On hold")
    assert [a.audience for a in built] == ["AP"]


def test_approved_run_without_audiences_sends_nothing(db, emails):
    ctx = run_sample(db, "01_happy_deccan.pdf")
    assert ctx.decision == "Approve"
    assert run_alerts(db, ctx.run_id) == [] and emails == []


def test_vendor_alert_stays_drafted_without_auto_send(db, emails, monkeypatch):
    monkeypatch.setattr(settings, "VENDOR_AUTO_SEND", False)
    ctx = run_sample(db, "04_edge_split_overbill_acme.pdf")
    (vendor,) = run_alerts(db, ctx.run_id)
    assert vendor.status == "Drafted" and vendor.sent_at is None
    assert emails == []


def test_internal_alerts_send_even_without_vendor_auto_send(db, emails, monkeypatch):
    monkeypatch.setattr(settings, "VENDOR_AUTO_SEND", False)
    ctx = run_sample(db, "06_edge_bank_changed_brighttech.pdf")
    assert {a.status for a in run_alerts(db, ctx.run_id)} == {"Sent"}
    assert len(emails) == 2


def test_resend_failure_marks_alert_failed_and_run_still_decides(db, monkeypatch):
    def down(*a, **k):
        raise ConnectionError("resend unreachable")

    monkeypatch.setattr(alerts, "_send_email", down)
    ctx = run_sample(db, "06_edge_bank_changed_brighttech.pdf")

    assert ctx.decision == "Hold"
    row = db.get(Invoice, ctx.run_id)
    assert row.status == "needs_review" and row.finished_at is not None
    rows = run_alerts(db, ctx.run_id)
    assert rows and {a.status for a in rows} == {"Failed"}
    assert not any(f.code == "sys" for f in ctx.findings)


def test_broken_alert_building_never_fails_the_run(db, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("template bug")

    monkeypatch.setattr(alerts, "build_alerts", broken)
    ctx = run_sample(db, "04_edge_split_overbill_acme.pdf")
    assert ctx.decision == "Hold" and db.get(Invoice, ctx.run_id).status == "needs_review"


def test_send_emails_off_leaves_everything_drafted(db, emails, monkeypatch):
    monkeypatch.setattr(settings, "SEND_EMAILS", False)
    ctx = run_sample(db, "06_edge_bank_changed_brighttech.pdf")
    assert {a.status for a in run_alerts(db, ctx.run_id)} == {"Drafted"}
    assert emails == []


def test_missing_resend_key_fails_the_alert_not_the_run(db, monkeypatch):
    monkeypatch.setattr(alerts, "_send_email", REAL_SEND)
    monkeypatch.setattr(alerts.resend.Emails, "send", lambda *a, **k: pytest.fail("network call attempted"))
    ctx = run_sample(db, "04_edge_split_overbill_acme.pdf")
    assert {a.status for a in run_alerts(db, ctx.run_id)} == {"Failed"}


def test_every_email_goes_to_the_owner(db, monkeypatch):
    calls = []
    monkeypatch.setattr(alerts, "_send_email", REAL_SEND)
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(settings, "OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(alerts.resend.Emails, "send", lambda params: calls.append(params) or {"id": "x"})
    ctx = run_sample(db, "06_edge_bank_changed_brighttech.pdf")

    assert len(calls) == 2
    assert all(c["to"] == ["owner@example.com"] and c["from"] == settings.EMAIL_FROM for c in calls)
    assert {a.to_email for a in run_alerts(db, ctx.run_id)} == {"owner@example.com"}


# --- Outbox API -----------------------------------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "MIN_STAGE_MS", 0)
    monkeypatch.setattr(run_service, "today", lambda: TODAY)
    seed.reset()
    with TestClient(app) as c:
        yield c


def post_sample(client, name: str) -> str:
    r = client.post("/api/runs", json={"sample_name": name})
    assert r.status_code == 202, r.text
    return r.json()["run_id"]


def test_outbox_lists_alerts_and_sends_drafted(client, emails, monkeypatch):
    monkeypatch.setattr(settings, "VENDOR_AUTO_SEND", False)
    run_id = post_sample(client, "04_edge_split_overbill_acme.pdf")

    listed = client.get("/api/alerts").json()
    assert len(listed) == 1
    alert = listed[0]
    assert alert["run_id"] == run_id and alert["status"] == "Drafted" and alert["invoice_no"] == "ACME/2026/0417"
    assert alert["audience"] == "Vendor" and alert["intended_for"] and alert["subject"] and alert["body"]
    assert client.get("/api/alerts", params={"status": "Sent"}).json() == []

    r = client.post(f"/api/alerts/{alert['alert_id']}/send")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "Sent" and r.json()["sent_at"]
    assert [e["subject"] for e in emails] == [alert["subject"]]
    assert client.post(f"/api/alerts/{alert['alert_id']}/send").status_code == 409
    assert client.post("/api/alerts/99999/send").status_code == 404

    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["alerts"][0]["status"] == "Sent"


def test_outbox_retries_a_failed_alert(client, emails, monkeypatch):
    def down(*a, **k):
        raise ConnectionError("resend unreachable")

    monkeypatch.setattr(alerts, "_send_email", down)
    post_sample(client, "04_edge_split_overbill_acme.pdf")
    (alert,) = client.get("/api/alerts", params={"status": "Failed"}).json()

    monkeypatch.setattr(alerts, "_send_email", lambda s, b: emails.append(s) or "ok")
    assert client.post(f"/api/alerts/{alert['alert_id']}/send").json()["status"] == "Sent"


def test_outbox_refuses_a_vendor_email_on_a_fraud_run(client):
    run_id = post_sample(client, "06_edge_bank_changed_brighttech.pdf")
    with SessionLocal() as s:  # a vendor draft that should never exist; the send must still refuse it
        s.add(Alert(run_id=run_id, audience="Vendor", to_email="x", subject="s", body="b", status="Drafted"))
        s.commit()
    vendor = next(a for a in client.get("/api/alerts").json() if a["audience"] == "Vendor")
    r = client.post(f"/api/alerts/{vendor['alert_id']}/send")
    assert r.status_code == 409 and "fraud" in r.json()["detail"]
