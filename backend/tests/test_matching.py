"""PO scoring (section 9 worked example), similarity cache and fallback, decision rules, runner rules."""

import pytest

from app import config, llm
from app.models import PurchaseOrder, Vendor
from app.pipeline import decide, runner
from app.pipeline.context import Finding, StageResult
from app.pipeline.runner import create_run
from app.services.matching import SOURCE_LLM, SOURCE_TEXT, SimTable, score_po, similarity_table
from app.utils.normalise import core_number, normalise_currency, po_candidates_from_ref
from tests.helpers import run_rules, run_sample, sample_extraction

SAMPLE_03 = "03_edge_inferred_po_acme.pdf"
CHAIR = "ErgoPro Mesh Ergonomic Chair"


# --- scoring --------------------------------------------------------------------

def _ctx_03(db):
    """Sample 03 up to the vendor, without running stage 5."""
    ctx = create_run(db, b"%PDF-03", "03.pdf")
    ctx.extraction = sample_extraction(SAMPLE_03)
    ctx.vendor = db.get(Vendor, "V-01")
    return ctx


def test_worked_example_scores_with_design_doc_similarities(db):
    """Section 9: similarity 0.9 / 0.4 / 0.0 gives 82.6 / 48.3 / 30.0."""
    ctx = _ctx_03(db)
    sims = SimTable({(CHAIR, "Ergonomic office chair, mesh back"): 0.9, (CHAIR, "Chair floor mat"): 0.1,
                     (CHAIR, "Standard office chair"): 0.4,
                     (CHAIR, "A4 copier paper 75gsm (ream of 500 sheets)"): 0.0})
    inv = ctx.inv
    got = {po_id: score_po(ctx, db.get(PurchaseOrder, po_id), sims, inv.total_paise, inv.invoice_date)
           for po_id in ("PO-2026-104", "PO-2026-117", "PO-2026-101")}
    assert got["PO-2026-104"].total == pytest.approx(82.6, abs=0.05)
    assert got["PO-2026-104"].line_points == pytest.approx(47.5)
    assert got["PO-2026-104"].amount_points == pytest.approx(23.8, abs=0.05)
    assert got["PO-2026-104"].date_points == pytest.approx(11.3, abs=0.05)
    assert got["PO-2026-117"].total == pytest.approx(48.3, abs=0.05)
    assert got["PO-2026-101"].total == pytest.approx(30.0, abs=0.05)
    top, second = got["PO-2026-104"].total, got["PO-2026-117"].total
    assert top >= config.PO_MATCH_MIN_SCORE and top - second >= config.PO_MATCH_MIN_GAP


def test_sample_03_end_to_end_with_committed_llm_scores(db):
    """The committed Gemini scores are 1.0 (not the doc's 0.9) for the mesh chair, so PO-104 is 85.1."""
    ctx = run_rules(db, sample_extraction(SAMPLE_03))
    assert ctx.llm_calls == 0
    scores = {s["po_id"]: s["total"] for s in next(f for f in ctx.findings if f.code == "5.7").evidence["scores"]}
    assert scores == {"PO-2026-104": pytest.approx(85.1), "PO-2026-117": pytest.approx(48.3),
                      "PO-2026-101": pytest.approx(30.0)}
    assert (ctx.po.po_id, ctx.match_type, ctx.match_confidence) == ("PO-2026-104", "Inferred", "High")


# --- similarity -------------------------------------------------------------------

def test_identical_text_needs_no_llm(db, monkeypatch):
    monkeypatch.setattr(llm, "similarity", lambda *a, **k: pytest.fail("LLM asked"))
    ctx = _ctx_03(db)
    table = similarity_table(ctx, [("27 inch IPS monitor", "27-inch IPS Monitor")])
    assert table.get("27 inch IPS monitor", "27-inch IPS Monitor") == 1.0 and table.source == SOURCE_LLM


def test_llm_failure_falls_back_to_rapidfuzz_and_lowers_confidence(db, monkeypatch):
    monkeypatch.setattr(llm, "SIM_CACHE_DIR", llm.SIM_CACHE_DIR / "does-not-exist")
    monkeypatch.setattr(config.settings, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(config.settings, "GEMINI_MODEL", "m1")
    monkeypatch.setattr(config.settings, "GEMINI_MODEL_FALLBACK", "")
    monkeypatch.setattr(llm, "_call_similarity_model", lambda *a: (_ for _ in ()).throw(RuntimeError("503")))
    ctx = run_rules(db, sample_extraction(SAMPLE_03))
    stage5 = next(f for f in ctx.findings if f.code == "5.7")
    assert stage5.evidence["similarity_source"] == SOURCE_TEXT
    assert (ctx.po.po_id, ctx.match_confidence) == ("PO-2026-104", "Medium")
    assert "compared by text only" in stage5.message
    assert ctx.llm_calls == 1 and ctx.decision == "Approve"


def test_similarity_respects_call_budget(db, monkeypatch):
    monkeypatch.setattr(config.settings, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(config.settings, "GEMINI_MODEL", "m1")
    ctx = _ctx_03(db)
    ctx.llm_calls = config.MAX_LLM_CALLS_PER_RUN
    assert llm.similarity([("never", "cached")], ctx) is None
    assert ctx.llm_calls == config.MAX_LLM_CALLS_PER_RUN


def test_similarity_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "SIM_CACHE_DIR", tmp_path)
    monkeypatch.setattr(config.settings, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(config.settings, "GEMINI_MODEL", "m1")
    calls = []
    monkeypatch.setattr(llm, "_call_similarity_model", lambda model, pairs: calls.append(model) or [0.7] * len(pairs))
    pairs = [("a chair", "office chair")]
    assert llm.similarity(pairs) == [0.7]
    assert llm.similarity(pairs) == [0.7]
    assert calls == ["m1"]
    assert (tmp_path / f"{llm.similarity_key(pairs)}.json").is_file()


# --- decision ---------------------------------------------------------------------

def F(code, severity, audience=(), fraud=False):
    return Finding(code, severity, f"message {code}", list(audience), fraud=fraud)


@pytest.mark.parametrize("severities,expected", [
    ([], "Approve"),
    (["pass", "info"], "Approve"),
    (["pass", "hold"], "Hold"),
    (["hold", "reject", "pass"], "Reject"),
    (["reject"], "Reject"),
])
def test_decision_precedence(severities, expected):
    assert decide.decide([F(str(i), s) for i, s in enumerate(severities)]) == expected


def test_reasons_put_rejects_first():
    findings = [F("6.5", "hold"), F("7.2", "reject"), F("8.1", "pass")]
    assert [r["code"] for r in decide.reasons(findings, "Reject")] == ["7.2", "6.5"]


def test_fraud_suppresses_vendor_audience():
    findings = [F("4.7", "hold", ["Finance", "AP"], fraud=True), F("3.2", "hold", ["Vendor"]), F("6.5", "hold", ["Vendor"])]
    audiences = decide.alert_audiences(findings)
    assert set(audiences) == {"Finance", "AP"}
    assert [f.code for f in audiences["AP"]] == ["4.7"]


def test_no_fraud_keeps_vendor_audience_grouped():
    audiences = decide.alert_audiences([F("6.5", "hold", ["Vendor"]), F("6.6", "hold", ["Vendor"])])
    assert [f.code for f in audiences["Vendor"]] == ["6.5", "6.6"]


def test_fraud_run_drops_vendor_alert_end_to_end(db):
    ex = sample_extraction("06_edge_bank_changed_brighttech.pdf")
    ex["invoice_date"] = None  # adds a Vendor-audience 3.2 alongside the 4.7 fraud hold
    ctx = run_rules(db, ex)
    assert "3.2" in ctx.codes()
    assert "Vendor" not in decide.alert_audiences(ctx.findings)


# --- runner -------------------------------------------------------------------------

def test_stage_error_becomes_system_error_hold_and_run_continues(db, monkeypatch):
    def broken(ctx):
        raise ValueError("boom")
    stages = list(runner.STAGES)
    stages[5] = ("Amounts and quantities", broken)
    monkeypatch.setattr(runner, "STAGES", stages)
    ctx = run_rules(db, sample_extraction("01_happy_deccan.pdf"))
    f = next(f for f in ctx.findings if f.code == "sys")
    assert f.label == "System error" and f.message.startswith("System error:")
    assert "boom" in f.evidence["error"]
    assert ctx.decision == "Hold"
    assert "9.1" in ctx.codes()  # later stages still ran


def test_only_stages_1_2_can_halt(db, monkeypatch):
    def halts(ctx):
        ctx.halt = True
        return StageResult("pass", "tried to halt")
    stages = list(runner.STAGES)
    stages[3] = ("Verify vendor", halts)
    monkeypatch.setattr(runner, "STAGES", stages)
    ctx = run_rules(db, sample_extraction("01_happy_deccan.pdf"))
    assert "9.1" in ctx.codes()


# --- normalisers --------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("PO 105", ["PO-2026-105", "PO-2025-105"]),
    ("PO118", ["PO-2026-118", "PO-2025-118"]),
    ("P.O. No: 2026/118", ["PO-2026-118"]),
    ("PO-2026-099", ["PO-2026-099"]),
    ("no number", []),
])
def test_po_candidates_from_ref(raw, expected):
    assert po_candidates_from_ref(raw, 2026) == expected


@pytest.mark.parametrize("raw,expected", [("SPH/INV-0042", "42"), ("42", "42"), ("INV-0042", "42"), ("", None)])
def test_core_number(raw, expected):
    assert core_number(raw) == expected


@pytest.mark.parametrize("raw,expected", [("Rs.", "INR"), ("Rs", "INR"), ("INR", "INR"), ("₹", "INR"),
                                          ("rs", "INR"), ("usd", "USD"), (None, None)])
def test_normalise_currency(raw, expected):
    assert normalise_currency(raw) == expected


def test_stage_2_stores_normalised_currency(db):
    ctx = run_sample(db, "02_happy_brighttech_scan.pdf")  # printed "Rs."
    assert ctx.extraction["currency"] == "INR"
