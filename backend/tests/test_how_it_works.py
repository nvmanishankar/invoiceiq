"""Part B of the "How it works" page: the permission matrix, the vendor loop and the facts match the code.

Every row of PERMISSIONS is exercised as each role, through the router (403 or not) or the review service
(403 / 409 or not), on a normal hold (sample 04) and a fraud hold (sample 06).
"""

import re
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import alerts, seed
from app.config import BACKEND_DIR, settings
from app.db import make_engine
from app.main import app
from app.models import Alert, Invoice
from app.roles import ROLES
from app.services import how_it_works, review
from app.services import runs as run_service
from tests.helpers import TODAY, run_sample

NORMAL = "04_edge_split_overbill_acme.pdf"
FRAUD = "06_edge_bank_changed_brighttech.pdf"
BY_KEY = {p["key"]: p for p in how_it_works.PERMISSIONS}


def allowed(key: str, role: str, fraud: bool = False) -> bool:
    p = BY_KEY[key]
    if fraud and p.get("fraud") == "nobody":
        return False
    rule = p.get("fraud") if fraud and p.get("fraud") else p["rule"]
    return rule == "anyone" or rule == {"Procurement": "procurement", "Finance": "finance"}.get(role)


def test_every_permission_is_well_formed():
    assert len(BY_KEY) == len(how_it_works.PERMISSIONS)
    for p in how_it_works.PERMISSIONS:
        assert p["rule"] in ("anyone", "procurement", "finance"), p["key"]
        assert p.get("fraud") in (None, "finance", "nobody"), p["key"]
        assert bool(p.get("fraud")) == bool(p.get("fraud_why")), p["key"]
        assert (BACKEND_DIR / "app" / p["where"]).is_file(), p["where"]


# --- Router guards: procurement and finance ---------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "MIN_STAGE_MS", 0)
    monkeypatch.setattr(run_service, "today", lambda: TODAY)
    seed.reset()
    with TestClient(app) as c:
        yield c


def _call(client, key: str, role: str):
    h = {"X-Role": role}
    if key == "create_po":
        return client.post("/api/pos", json={}, headers=h)
    if key == "po_status":
        po = client.get("/api/pos").json()[0]["po_id"]
        return client.patch(f"/api/pos/{po}", json={"status": "Closed"}, headers=h)
    if key == "add_vendor":
        return client.post("/api/vendors", json={}, headers=h)
    if key == "vendor_status":
        vid = client.get("/api/vendors").json()[0]["vendor_id"]
        return client.patch(f"/api/vendors/{vid}", json={"status": "Blocked"}, headers=h)
    if key == "tolerance":
        return client.patch("/api/settings", json={"tolerance_pct": 2}, headers=h)
    if key == "auto_send":
        return client.patch("/api/settings", json={"vendor_auto_send": True}, headers=h)
    raise KeyError(key)


@pytest.mark.parametrize("key", ["create_po", "po_status", "add_vendor", "vendor_status", "tolerance", "auto_send"])
def test_router_guards_match_the_matrix(client, key):
    for role in ROLES:
        r = _call(client, key, role)
        assert (r.status_code != 403) == allowed(key, role), (key, role, r.status_code, r.text)


def test_no_header_is_never_more_powerful_than_ap_clerk(client):
    assert client.post("/api/pos", json={}).status_code == 403
    assert client.patch("/api/settings", json={"tolerance_pct": 2}).status_code == 403


# --- Review actions, on a normal hold and a fraud hold ------------------------------------------------------------

def _fresh(db, sample: str) -> Invoice:
    ctx = run_sample(db, sample)
    assert ctx.decision == "Hold"
    return db.get(Invoice, ctx.run_id)


def _do(db, key: str, row: Invoice, role: str) -> int:
    """HTTP-like status of doing `key` on `row` as `role`: 200, or the ReviewError / VendorEmailBlocked status."""
    try:
        if key == "confirm":
            review.apply(db, row.run_id, "confirm", role, fields={})
        elif key == "pick_po":
            review.apply(db, row.run_id, "pick_po", role, po_id=row.po_id)
        elif key == "override":  # the role rules, not the PO balance (sample 04 is over it; that has its own tests)
            review.apply(db, row.run_id, key, role, reason="checked", confirm_over_budget=True)
        elif key == "reject":
            review.apply(db, row.run_id, key, role, reason="checked")
        elif key in ("send_to_vendor", "send_reminder"):
            if key == "send_reminder" and not review._has_fraud(review._stages(db, row.run_id)):
                _send(db, row, "AP clerk")  # a reminder needs an earlier email
            if key == "send_to_vendor":
                _send(db, row, role)
            else:
                review.apply(db, row.run_id, "send_reminder", role)
        elif key == "corrected":
            review.supersede(db, row, role, "RUN-NEW")
            db.rollback()
        elif key == "outbox_send":
            alert = Alert(run_id=row.run_id, audience="Vendor", intended_for="x", to_email=settings.OWNER_EMAIL,
                          subject="s", body="b", status="Drafted")
            db.add(alert)
            db.commit()
            alerts.send_drafted(db, alert)
        else:
            raise KeyError(key)
    except review.ReviewError as e:
        db.rollback()
        return e.status
    except alerts.VendorEmailBlocked:
        db.rollback()
        return 409
    return 200


def _send(db, row: Invoice, role: str) -> None:
    try:
        preview = review.email_preview(db, row.run_id)
    except review.ReviewError:
        # a fraud run has no preview; the action must refuse anyway
        preview = {"selected": ["other"], "note": "x", "subject": "s", "body": "b"}
    review.apply(db, row.run_id, "send_to_vendor", role, reasons=preview["selected"], note=preview["note"],
                 subject=preview["subject"], body=preview["body"])


REVIEW_KEYS = [p["key"] for p in how_it_works.PERMISSIONS if p["where"] in ("services/review.py", "routers/alerts.py")]


# Every review action on a normal hold; on a fraud hold, the ones with a fraud rule.
CASES = [(k, NORMAL) for k in REVIEW_KEYS] + [(k, FRAUD) for k in REVIEW_KEYS if BY_KEY[k].get("fraud")]


@pytest.mark.parametrize("key,sample", CASES, ids=[f"{'fraud' if s == FRAUD else 'hold'}-{k}" for k, s in CASES])
def test_review_actions_match_the_matrix(key, sample):
    fraud = sample == FRAUD
    for role in ROLES:
        engine = make_engine("sqlite://")  # a fresh copy per role: the same sample twice would be a duplicate
        seed.reset(engine)
        with Session(engine) as db:
            status = _do(db, key, _fresh(db, sample), role)
        engine.dispose()
        assert (status == 200) == allowed(key, role, fraud), (key, role, sample, status)
        if not allowed(key, role, fraud):
            assert status in (403, 409)


def test_matrix_lists_every_review_action():
    listed = {p["key"] for p in how_it_works.PERMISSIONS}
    assert set(review.ACTIONS) <= listed
    assert {"corrected", "outbox_send"} <= listed


# --- Vendor loop and facts ------------------------------------------------------------------------------------------

def test_vendor_loop_is_sample_04_as_the_code_renders_it():
    v = how_it_works.vendor_loop()
    assert v["decision"] == "Hold"
    assert {f["code"] for f in v["findings"]} == {"6.5", "6.6"}
    body = v["email"]["body"]
    assert "Note from our AP team:" in body and alerts.LINK_PENDING in body
    for f in v["findings"]:
        assert f["message"] in body
    assert v["response_page"]["issues"] == [f["message"] for f in v["findings"]]
    assert "bank" not in str(v["response_page"]).lower()  # vendor-safe fields only
    assert v["protected"]["category"] == "overbilling"
    assert v["protected"]["paise"] == v["total_paise"] - v["remaining_paise"]


def test_facts_quote_the_code():
    f = how_it_works.facts()
    assert f["token_days"] == alerts.TOKEN_DAYS == 7
    assert f["resume"] == {"confirm": 3, "pick_po": 6}
    assert f["tests"]["samples"] == 10


def test_automated_test_count_is_current():
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
                         cwd=BACKEND_DIR, capture_output=True, text=True, timeout=120).stdout
    n = int(re.search(r"(\d+) tests? collected", out).group(1))
    assert how_it_works.AUTOMATED_TESTS == n, f"Set AUTOMATED_TESTS = {n} in app/services/how_it_works.py"


def test_vendor_loop_leaves_no_vendor_email_on_fraud(db):
    row = _fresh(db, FRAUD)
    assert not db.scalars(select(Alert).where(Alert.run_id == row.run_id, Alert.audience == "Vendor")).all()
