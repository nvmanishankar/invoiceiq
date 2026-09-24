"""Phase 13: the in-app test suite on a scratch database, and Finance-only tolerance, offline."""

import shutil

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import llm, seed
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Alert, CompanySettings, Invoice, PurchaseOrder, RunStage, Vendor
from app.pipeline.runner import file_hash
from app.services import runs as run_service
from app.services import test_suite
from tests.helpers import EXPECTED, SAMPLES, TODAY


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "MIN_STAGE_MS", 0)
    monkeypatch.setattr(run_service, "today", lambda: TODAY)
    monkeypatch.setattr(test_suite, "_last_finished", None)  # no cool-down left over from another test
    seed.reset()
    with TestClient(app) as c:
        yield c


def live_snapshot() -> dict:
    with SessionLocal() as db:
        def count(model):
            return db.scalar(select(func.count()).select_from(model))
        c = db.scalar(select(CompanySettings))
        return {
            "invoices": count(Invoice), "stages": count(RunStage), "alerts": count(Alert), "pos": count(PurchaseOrder),
            "vendors": count(Vendor), "runs_today": run_service.runs_today(db),
            "alert_rows": [(a.alert_id, a.status) for a in db.scalars(select(Alert))],
            "settings": (c.tolerance_pct, c.tolerance_abs_paise, c.vendor_auto_send),
        }


def test_suite_passes_every_sample_offline(client, emails):
    r = client.post("/api/admin/test-suite")
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["passed"], body["total"]) == (10, 10)
    assert body["duration_ms"] >= 0 and body["ran_at"]
    assert [x["file"] for x in body["results"]] == [e["file"] for e in EXPECTED]
    for row, exp in zip(body["results"], EXPECTED):
        assert row["passed"] and row["error"] is None, row
        assert row["actual_decision"] == exp["decision"] and row["missing_codes"] == []
        assert set(exp["codes"]) <= set(row["actual_codes"])
        assert row["llm_calls"] == 0
        assert row["stages"][0]["name"] == "Read document" and row["stages"][-1]["name"] == "Decision"
        assert all(set(s) == {"name", "status", "message"} for s in row["stages"])
        if "po_id" in exp:
            assert row["expected_po_id"] == row["actual_po_id"] == exp["po_id"]
        if "due_date" in exp:
            assert row["expected_due_date"] == row["actual_due_date"] == exp["due_date"]
    assert emails == []


def test_suite_leaves_the_live_database_untouched(client, emails, monkeypatch):
    run_id = client.post("/api/runs", json={"sample_name": "04_edge_split_overbill_acme.pdf"}).json()["run_id"]
    client.patch("/api/settings", json={"tolerance_cap": 3000}, headers={"X-Role": "Finance"})
    sent_before = len(emails)
    assert sent_before == 1  # the live run's vendor email
    before = live_snapshot()

    assert client.post("/api/admin/test-suite").json()["passed"] == 10

    assert live_snapshot() == before
    assert len(emails) == sent_before
    with SessionLocal() as db:
        assert db.get(Invoice, run_id).decision == "Hold"


def test_missing_cache_fails_the_row_without_calling_gemini(client, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(settings, "GEMINI_MODEL", "test-model")
    monkeypatch.setattr(llm, "_call_model", lambda *a, **k: calls.append("extract"))
    monkeypatch.setattr(llm, "_call_similarity_model", lambda *a, **k: calls.append("similarity"))
    # A copy of the extraction cache without sample 01's file.
    missing = file_hash((SAMPLES / "01_happy_deccan.pdf").read_bytes())
    cache = tmp_path / "extractions"
    shutil.copytree(llm.CACHE_DIR, cache, ignore=lambda _d, names: [n for n in names if n.startswith(missing)])
    monkeypatch.setattr(llm, "CACHE_DIR", cache)

    body = client.post("/api/admin/test-suite").json()

    first = body["results"][0]
    assert first["file"] == "01_happy_deccan.pdf" and not first["passed"]
    assert first["error"] == "No cached extraction for this sample" and first["actual_decision"] is None
    assert first["missing_codes"] == first["expected_codes"]
    assert body["passed"] == 9
    assert calls == []


def test_second_suite_while_one_is_running_gets_409(client):
    assert test_suite._lock.acquire(blocking=False)
    try:
        r = client.post("/api/admin/test-suite")
    finally:
        test_suite._lock.release()
    assert r.status_code == 409 and "already running" in r.json()["detail"]


def test_suite_has_a_short_cool_down(client):
    assert client.post("/api/admin/test-suite").status_code == 200
    again = client.post("/api/admin/test-suite")
    assert again.status_code == 429 and int(again.headers["Retry-After"]) >= 1
    assert "wait" in again.json()["detail"]


@pytest.mark.parametrize("headers", [{}, {"X-Role": "AP clerk"}, {"X-Role": "Procurement"}])
def test_only_finance_changes_tolerance(client, headers):
    r = client.patch("/api/settings", json={"tolerance_pct": 1}, headers=headers)
    assert r.status_code == 403 and "Only Finance can change the tolerance" in r.json()["detail"]
    assert client.get("/api/settings").json()["tolerance_pct"] == 2

    ok = client.patch("/api/settings", json={"tolerance_pct": 1}, headers={"X-Role": "Finance"})
    assert ok.status_code == 200 and ok.json()["tolerance_pct"] == 1


@pytest.mark.parametrize("role", ["AP clerk", "Finance"])
def test_auto_send_toggle_stays_open(client, role):
    r = client.patch("/api/settings", json={"vendor_auto_send": False}, headers={"X-Role": role})
    assert r.status_code == 200 and r.json()["vendor_auto_send"] is False
