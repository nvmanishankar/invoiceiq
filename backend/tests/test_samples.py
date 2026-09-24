"""All 10 samples end to end on committed fixtures: decision and must-have codes from expected.json.

Codes in expected.json are "must include", not "only these" (docs/SEED_KIT_README.md).
"""

import pytest

from app.models import Invoice, RunStage
from tests.helpers import EXPECTED, run_sample


@pytest.mark.parametrize("exp", EXPECTED, ids=[e["file"][:2] for e in EXPECTED])
def test_sample(db, exp):
    ctx = run_sample(db, exp["file"])
    codes = ctx.codes()

    assert ctx.decision == exp["decision"], [(f.code, f.severity, f.message) for f in ctx.findings]
    assert set(exp["codes"]) <= set(codes), f"missing {set(exp['codes']) - set(codes)}; got {codes}"
    assert ctx.llm_calls == 0  # fixtures only
    assert "sys" not in codes

    row = db.get(Invoice, ctx.run_id)
    assert row.decision == exp["decision"]
    assert row.status == {"Approve": "approved", "Hold": "needs_review", "Reject": "rejected"}[exp["decision"]]
    if "po_id" in exp:
        assert row.po_id == exp["po_id"]
    if "match_type" in exp:
        assert row.po_match_type == exp["match_type"]
    if "confidence" in exp:
        assert row.match_confidence == exp["confidence"]
    if "due_date" in exp:
        assert row.due_date.isoformat() == exp["due_date"]
    if "duplicate_of" in exp:
        assert exp["duplicate_of"] in {f.evidence.get("duplicate_of") for f in ctx.findings}

    decision_stage = db.query(RunStage).filter_by(run_id=ctx.run_id, stage_name="Decision").one()
    alerts = decision_stage.details["alerts"]
    assert set(exp.get("alerts", [])) <= set(alerts)
    if exp.get("no_vendor_email"):
        assert "Vendor" not in alerts
    if exp.get("fraud"):
        assert decision_stage.details["fraud"] is True


def test_sample_07_halts_at_stage_2_and_still_decides(db):
    ctx = run_sample(db, "07_extra_quotation_acme.pdf")
    stages = [s.stage_name for s in db.query(RunStage).filter_by(run_id=ctx.run_id).order_by(RunStage.stage_order)]
    assert stages == ["Read document", "Extract fields", "Decision"]


def test_sample_05_also_flags_fully_billed_po(db):
    ctx = run_sample(db, "05_edge_duplicate_sahyadri_scan.pdf")
    assert {"7.2", "6.5"} <= set(ctx.codes())


def test_sample_10_also_flags_po_not_found(db):
    ctx = run_sample(db, "10_extra_blocked_quickfix.pdf")
    assert "5.3" in ctx.codes()
    assert "4.1" not in ctx.codes()  # a blocked vendor isn't reported as approved


def test_running_01_twice_rejects_the_second(db):
    first = run_sample(db, "01_happy_deccan.pdf")
    assert first.decision == "Approve"
    second = run_sample(db, "01_happy_deccan.pdf")
    assert second.decision == "Reject"
    f = next(f for f in second.findings if f.code == "7.1")
    assert f.severity == "reject" and f.evidence["duplicate_of"] == first.run_id
    assert "7.2" not in second.codes()  # the same prior isn't reported twice
    assert "6.5" in second.codes()  # the first run used up PO-2026-109
