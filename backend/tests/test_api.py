"""API and SSE, offline on committed fixtures (build guide section 12)."""

import json
import threading

import pytest
from fastapi.testclient import TestClient

from app import seed
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Invoice
from app.services import runs as run_service
from tests.helpers import EXPECTED, SAMPLES, TODAY

EXPECTED_BY_FILE = {e["file"]: e for e in EXPECTED}


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
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                events.append((event, json.loads(line[6:])))
    return events


def post_sample(client, name: str) -> str:
    r = client.post("/api/runs", json={"sample_name": name})
    assert r.status_code == 202, r.text
    return r.json()["run_id"]


@pytest.mark.parametrize("exp", EXPECTED, ids=[e["file"][:2] for e in EXPECTED])
def test_sample_streams_in_order_and_decides_as_expected(client, exp):
    events = read_stream(client, post_sample(client, exp["file"]))
    kinds = [k for k, _ in events]

    assert kinds[-2:] == ["decision", "done"]
    assert set(kinds[:-2]) == {"stage"}
    stages = [d for k, d in events if k == "stage"]
    orders = [s["order"] for s in stages]
    assert orders == sorted(orders) and len(set(orders)) == len(orders)
    assert stages[0]["name"] == "Read document" and stages[-1]["name"] == "Decision"

    decision = events[-2][1]
    assert decision["decision"] == exp["decision"]
    assert decision["headline"]
    codes = {f["code"] for s in stages for f in s["details"]["findings"]}
    assert set(exp["codes"]) <= codes


def test_sample_07_halts_after_stage_2_in_the_stream(client):
    events = read_stream(client, post_sample(client, "07_extra_quotation_acme.pdf"))
    assert [d["name"] for k, d in events if k == "stage"] == ["Read document", "Extract fields", "Decision"]


def test_second_viewer_gets_the_same_replay(client):
    run_id = post_sample(client, "04_edge_split_overbill_acme.pdf")
    assert read_stream(client, run_id) == read_stream(client, run_id)


def test_stream_follows_a_run_while_it_is_still_going(client, monkeypatch):
    monkeypatch.setattr(settings, "MIN_STAGE_MS", 30)
    run_id = run_service.start_run((SAMPLES / "01_happy_deccan.pdf").read_bytes(), "01_happy_deccan.pdf")
    worker = threading.Thread(target=run_service.execute_run, args=(run_id,))
    worker.start()
    events = read_stream(client, run_id)
    worker.join()
    assert [k for k, _ in events][-2:] == ["decision", "done"]
    assert len([k for k, _ in events if k == "stage"]) == 10
    assert events[-2][1]["decision"] == "Approve"


def test_upload_pdf_multipart(client):
    pdf = (SAMPLES / "02_happy_brighttech_scan.pdf").read_bytes()
    r = client.post("/api/runs", files={"file": ("my invoice.pdf", pdf, "application/pdf")})
    assert r.status_code == 202, r.text
    run_id = r.json()["run_id"]

    events = read_stream(client, run_id)
    assert events[-2][1]["decision"] == "Approve"

    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["status"] == "approved" and detail["file_name"] == "my invoice.pdf" and detail["has_file"]

    f = client.get(f"/api/runs/{run_id}/file")
    assert f.status_code == 200
    assert f.headers["content-type"] == "application/pdf"
    assert f.headers["content-disposition"].startswith("inline")
    assert f.content == pdf


def test_sample_name_as_form_field(client):
    r = client.post("/api/runs", data={"sample_name": "01_happy_deccan.pdf"})
    assert r.status_code == 202, r.text


def test_run_detail_has_matched_po_with_remaining_balance(client):
    exp = EXPECTED_BY_FILE["04_edge_split_overbill_acme.pdf"]
    run_id = post_sample(client, exp["file"])
    d = client.get(f"/api/runs/{run_id}").json()

    assert d["decision"]["decision"] == exp["decision"]
    assert d["total_paise"] == exp["total_paise"]
    assert d["total_display"].startswith("₹")
    assert len(d["stages"]) == 10 and d["lines"]
    assert all("stage_name" in f and "message" in f for f in d["findings"])
    assert "6.5" in {f["code"] for f in d["findings"]}

    po = d["po"]
    assert po["po_id"] == exp["po_id"]
    assert po["lines"] and po["previous_invoices"]
    invoiced = sum(p["total_paise"] for p in po["previous_invoices"] if p["counts_against_po"])
    assert po["invoiced_before_paise"] == invoiced
    assert po["remaining_before_paise"] == po["total_paise"] - invoiced
    assert po["remaining_before_paise"] < d["total_paise"]  # the over-billing this sample is about
    assert po["remaining_paise"] == po["remaining_before_paise"]  # held, so nothing more used
    assert po["remaining_before_display"].startswith("₹")
    assert any(row["invoice_line"] and row["po_line"] for row in d["comparison"])
    assert "Vendor" in d["alert_groups"]["by_audience"]


def test_run_detail_approved_run_uses_up_the_po(client):
    run_id = post_sample(client, "01_happy_deccan.pdf")
    read_stream(client, run_id)
    po = client.get(f"/api/runs/{run_id}").json()["po"]
    assert po["remaining_paise"] == po["remaining_before_paise"] - 26550000


def test_fraud_run_suppresses_vendor_alert(client):
    run_id = post_sample(client, "06_edge_bank_changed_brighttech.pdf")
    groups = client.get(f"/api/runs/{run_id}").json()["alert_groups"]
    assert groups["fraud"] is True
    assert "Vendor" not in groups["by_audience"] and "Finance" in groups["by_audience"]


def test_list_filters_and_excludes_seed(client):
    a = post_sample(client, "01_happy_deccan.pdf")
    b = post_sample(client, "06_edge_bank_changed_brighttech.pdf")

    runs = client.get("/api/runs").json()
    assert [r["run_id"] for r in runs] == [b, a]  # newest first, no seed ledger rows
    assert [r["run_id"] for r in client.get("/api/runs", params={"status": "approved"}).json()] == [a]
    assert [r["run_id"] for r in client.get("/api/runs", params={"vendor": "BrightTech"}).json()] == [b]
    assert [r["run_id"] for r in client.get("/api/runs", params={"q": "DOI/2026"}).json()] == [a]
    with_seed = client.get("/api/runs", params={"include_seed": True}).json()
    assert len(with_seed) > 2 and any(r["is_seed"] for r in with_seed)


def test_samples_list(client):
    samples = client.get("/api/samples").json()
    assert len(samples) == 10
    assert samples[0]["file"] == "01_happy_deccan.pdf" and samples[0]["expected_decision"] == "Approve"
    assert all(s["story"] for s in samples)


def test_daily_cap_returns_429(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_RUNS_PER_DAY", 2)
    post_sample(client, "01_happy_deccan.pdf")
    post_sample(client, "02_happy_brighttech_scan.pdf")
    r = client.post("/api/runs", json={"sample_name": "03_edge_inferred_po_acme.pdf"})
    assert r.status_code == 429
    assert "2 invoices a day" in r.json()["detail"]


def test_bad_requests(client):
    assert client.post("/api/runs", json={"sample_name": "../app/main.py"}).status_code == 404
    assert client.post("/api/runs", json={}).status_code == 400
    assert client.post("/api/runs", content=b"x", headers={"content-type": "text/plain"}).status_code == 415
    assert client.get("/api/runs/RUN-NOPE").status_code == 404
    assert client.get("/api/runs/RUN-NOPE/stream").status_code == 404
    assert client.get("/api/runs/RUN-NOPE/file").status_code == 404


def test_reset_restores_seed(client):
    post_sample(client, "01_happy_deccan.pdf")
    assert client.get("/api/runs").json()

    assert client.post("/api/admin/reset", json={"confirm": "yes"}).status_code == 400
    r = client.post("/api/admin/reset", json={"confirm": "RESET"})
    assert r.status_code == 200 and r.json()["ok"]

    assert client.get("/api/runs").json() == []
    ledger = json.loads((seed.SEED_DIR / "ledger.json").read_text(encoding="utf-8"))
    assert len(client.get("/api/runs", params={"include_seed": True}).json()) == len(ledger)
    # The same sample approves again because its earlier approval was wiped.
    events = read_stream(client, post_sample(client, "01_happy_deccan.pdf"))
    assert events[-2][1]["decision"] == "Approve"


def test_interrupted_run_is_closed_on_startup(client):
    run_id = run_service.start_run((SAMPLES / "01_happy_deccan.pdf").read_bytes(), "01_happy_deccan.pdf")
    with SessionLocal() as db:
        assert run_service.recover_interrupted_runs(db) == 1
        assert db.get(Invoice, run_id).status == "needs_review"
    events = read_stream(client, run_id)
    assert [k for k, _ in events] == ["stage", "decision", "done"]
    assert events[1][1]["reasons"][0]["code"] == "sys"
