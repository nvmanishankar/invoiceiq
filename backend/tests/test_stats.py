"""Dashboard stats (build guide section 13) and API timestamps, offline on committed fixtures."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, func, select

from app.models import Invoice, Review
from app.services import review as review_service
from app.services.stats import compute
from app.utils.timefmt import iso
from tests.helpers import EXPECTED, run_sample

PROTECTED = {"04": 2360000, "05": 7080000, "06": 24780000}  # ₹23,600 · ₹70,800 · ₹2,47,800


@pytest.fixture
def ran(db):
    """Samples 01-10 on one fresh DB (seed ledger included). Returns {"01": run_id, ...}."""
    return {e["file"][:2]: run_sample(db, e["file"]).run_id for e in EXPECTED}


def test_kpis_after_all_ten_samples(db, ran):
    k = compute(db)["kpis"]
    assert k["processed"] == 10
    assert (k["approved"], k["held"], k["rejected"]) == (3, 4, 3)
    assert k["open_review"] == 4 and k["waiting_on_vendor"] == 0 and k["in_progress"] == 0
    assert k["touchless"] == 3 and k["touchless_rate"] == 0.3
    assert k["time_saved"] == {"minutes": 80, "hours": 1.3, "minutes_per_invoice": 8,
                               "assumption": "8 minutes of manual AP work per invoice"}
    assert k["avg_processing_seconds"] is not None


def test_seed_ledger_is_excluded(db, ran):
    seeded = db.scalar(select(func.count()).select_from(Invoice).where(Invoice.is_seed.is_(True)))
    assert seeded > 0
    s = compute(db)
    assert s["kpis"]["processed"] == 10
    assert sum(d["Approve"] + d["Hold"] + d["Reject"] for d in s["series"]["decisions_per_day"]) == 10


def test_money_protected(db, ran):
    mp = compute(db)["kpis"]["money_protected"]
    by_key = {b["key"]: b for b in mp["breakdown"]}
    # 05 also carries 6.5 (over the PO balance) but counts once, as a duplicate.
    assert by_key["duplicates"]["paise"] == PROTECTED["05"] and by_key["duplicates"]["runs"] == 1
    assert by_key["overbilling"]["paise"] == PROTECTED["04"] and by_key["overbilling"]["runs"] == 1
    assert by_key["fraud"]["paise"] == PROTECTED["06"] and by_key["fraud"]["runs"] == 1
    assert mp["paise"] == sum(PROTECTED.values())
    assert mp["display"] == "₹3,42,200"
    assert by_key["overbilling"]["display"] == "₹23,600"
    assert by_key["fraud"]["display"] == "₹2,47,800"


def test_touchless_counts_only_runs_without_review(db, ran):
    db.add(Review(run_id=ran["01"], reviewer="AP clerk", action="confirm", reason="checked by hand"))
    db.commit()
    k = compute(db)["kpis"]
    assert k["approved"] == 3
    assert k["touchless"] == 2


def test_overridden_run_is_not_touchless(db, ran):
    review_service.apply(db, ran["08"], "override", "AP clerk", reason="Vendor confirmed; reissue not needed")
    db.commit()
    k = compute(db)["kpis"]
    assert k["approved"] == 4 and k["held"] == 3
    assert k["touchless"] == 3


def test_overridden_overbilling_is_no_longer_protected(db, ran):
    review_service.apply(db, ran["04"], "override", "AP clerk", reason="PO amendment on the way")
    db.commit()
    mp = compute(db)["kpis"]["money_protected"]
    assert mp["paise"] == PROTECTED["05"] + PROTECTED["06"]


def test_top_reasons_and_health(db, ran):
    s = compute(db)
    top = {r["code"]: r for r in s["series"]["top_reasons"]}
    assert top["6.5"]["count"] == 2 and top["6.5"]["title"] == "Over PO balance"
    assert top["4.7"]["title"] == "Bank account changed"
    assert top["1.4"]["reject"] == 1
    assert "8.1" not in top  # passes aren't reasons
    counts = [r["count"] for r in s["series"]["top_reasons"]]
    assert counts == sorted(counts, reverse=True)
    h = s["health"]
    assert h["low_confidence_share"] == 0 and h["system_error_share"] == 0
    assert h["llm_calls_per_run"] == 0  # fixtures only
    assert h["avg_stage_ms"] is not None


def test_empty_db(db):
    s = compute(db)
    assert s["kpis"]["processed"] == 0 and s["kpis"]["touchless_rate"] is None
    assert s["kpis"]["money_protected"]["paise"] == 0
    assert len(s["series"]["decisions_per_day"]) == 14


def test_days_follow_the_viewers_timezone(db, ran):
    # 20:00 UTC on 23 Sep is 01:30 on 24 Sep in India.
    row = db.get(Invoice, ran["01"])
    row.created_at = datetime(2026, 9, 23, 20, 0)
    db.commit()
    now = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    utc = {d["date"]: d for d in compute(db, 0, now=now)["series"]["decisions_per_day"]}
    ist = {d["date"]: d for d in compute(db, 330, now=now)["series"]["decisions_per_day"]}
    assert utc["2026-09-23"]["Approve"] == 1
    assert ist["2026-09-23"]["Approve"] == 0


def test_stats_use_a_fixed_number_of_queries(db, engine, ran):
    for i in range(30):
        run_sample(db, "01_happy_deccan.pdf")  # more runs must not mean more queries
    statements = []
    listener = lambda *a: statements.append(a[2])  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        compute(db)
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    assert len(statements) <= 3


def test_naive_and_aware_datetimes_serialise_the_same():
    naive = datetime(2026, 9, 24, 8, 15, 30)
    aware = datetime(2026, 9, 24, 8, 15, 30, tzinfo=timezone.utc)
    ist = aware.astimezone(timezone(timedelta(hours=5, minutes=30)))
    assert iso(naive) == iso(aware) == iso(ist) == "2026-09-24T08:15:30+00:00"
    assert iso(None) is None
    assert iso(aware.date()) == "2026-09-24"


def test_stats_endpoint_and_api_timestamps_carry_an_offset(monkeypatch):
    from fastapi.testclient import TestClient

    from app import seed
    from app.config import settings
    from app.main import app
    from app.services import runs as run_service
    from tests.helpers import TODAY

    monkeypatch.setattr(settings, "MIN_STAGE_MS", 0)
    monkeypatch.setattr(run_service, "today", lambda: TODAY)
    seed.reset()
    with TestClient(app) as client:
        r = client.post("/api/runs", json={"sample_name": "01_happy_deccan.pdf"})
        run_id = r.json()["run_id"]
        s = client.get("/api/stats", params={"tz_offset": 330}).json()
        assert s["kpis"]["processed"] == 1 and s["kpis"]["touchless"] == 1
        run = client.get(f"/api/runs/{run_id}").json()
        listed = client.get("/api/runs").json()
    for stamp in (run["created_at"], run["finished_at"], run["stages"][0]["created_at"], listed[0]["created_at"]):
        assert stamp.endswith("+00:00"), stamp
    assert client.get("/api/stats", params={"tz_offset": 99999}).status_code == 422
