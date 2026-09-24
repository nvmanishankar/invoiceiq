"""LLM cache, fallback and graceful failure, plus stages 1-2 on cached fixtures. No network."""

import json
import logging
from pathlib import Path

import pytest

from app import llm
from app.config import BACKEND_DIR, settings
from app.pipeline.runner import create_run, file_hash, run_pipeline
from app.schemas import ExtractedInvoice, Extraction
from app.utils.money import rupees_to_paise

SAMPLES = BACKEND_DIR / "samples"
FIXTURES = BACKEND_DIR / "fixtures" / "extractions"
EXPECTED = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))
FAKE_KEY = "test-key-SHOULD-NOT-APPEAR"


def _sample_extraction() -> Extraction:
    return Extraction(doc_type="invoice", invoices=[ExtractedInvoice(invoice_number="INV-1", total=118.0)])


@pytest.fixture
def no_network(monkeypatch):
    """Fail loudly if anything reaches the real model."""
    def boom(*a, **k):
        raise AssertionError("network call attempted")
    monkeypatch.setattr(llm, "_call_model", boom)


@pytest.fixture
def tmp_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", FAKE_KEY)
    monkeypatch.setattr(settings, "GEMINI_MODEL", "primary-model")
    monkeypatch.setattr(settings, "GEMINI_MODEL_FALLBACK", "fallback-model")
    return tmp_path


# --- cache -------------------------------------------------------------------

def test_cache_hit_skips_model(tmp_cache, no_network):
    llm.save_cache("abc", _sample_extraction(), "primary-model", "x.pdf")
    got = llm.extract(b"%PDF", "abc")
    assert got.invoices[0].invoice_number == "INV-1"


def test_cache_miss_calls_once_then_caches(tmp_cache, monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "_call_model", lambda model, *a: calls.append(model) or _sample_extraction())
    assert llm.extract(b"%PDF", "h1").invoices[0].total == 118.0
    assert llm.extract(b"%PDF", "h1").invoices[0].total == 118.0
    assert calls == ["primary-model"]
    saved = json.loads((tmp_cache / "h1.json").read_text())
    assert saved["model"] == "primary-model" and saved["file_hash"] == "h1"


def test_corrupt_cache_file_is_a_miss(tmp_cache, monkeypatch):
    (tmp_cache / "bad.json").write_text("{not json")
    monkeypatch.setattr(llm, "_call_model", lambda *a: _sample_extraction())
    assert llm.extract(b"%PDF", "bad") is not None


# --- fallback and graceful failure --------------------------------------------

def test_fallback_model_used_when_primary_fails(tmp_cache, monkeypatch):
    calls = []

    def fake(model, *a):
        calls.append(model)
        if model == "primary-model":
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return _sample_extraction()

    monkeypatch.setattr(llm, "_call_model", fake)
    assert llm.extract(b"%PDF", "h2") is not None
    assert calls == ["primary-model", "fallback-model"]


def test_all_models_fail_returns_none_without_leaking_key(tmp_cache, monkeypatch, caplog):
    def fake(model, *a):
        raise RuntimeError(f"server error for key={FAKE_KEY}")

    monkeypatch.setattr(llm, "_call_model", fake)
    with caplog.at_level(logging.WARNING, logger="app.llm"):
        assert llm.extract(b"%PDF", "h3") is None
    assert FAKE_KEY not in caplog.text
    assert "failed" in caplog.text
    assert not (tmp_cache / "h3.json").exists()


def test_no_api_key_returns_none(tmp_cache, monkeypatch, no_network):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    assert llm.extract(b"%PDF", "h4") is None


def test_stage2_holds_when_extraction_unavailable(db, tmp_cache, monkeypatch):
    monkeypatch.setattr(llm, "_call_model", lambda *a: (_ for _ in ()).throw(RuntimeError("503")))
    ctx = create_run(db, (SAMPLES / "01_happy_deccan.pdf").read_bytes(), "01.pdf")
    run_pipeline(ctx, min_stage_ms=0)
    assert ctx.halt
    assert ctx.llm_calls == 2
    assert [(f.code, f.severity) for f in ctx.findings] == [("2.2", "hold")]


# --- stages 1-2 ---------------------------------------------------------------

def test_stage1_corrupt_file_rejects(db, no_network):
    ctx = create_run(db, b"not a pdf at all", "junk.pdf")
    run_pipeline(ctx, min_stage_ms=0)
    assert ctx.halt
    assert [(f.code, f.severity) for f in ctx.findings] == [("1.3", "reject")]


def test_pipeline_on_cached_happy_invoices(db, no_network):
    ctx = create_run(db, (SAMPLES / "02_happy_brighttech_scan.pdf").read_bytes(), "02.pdf")
    run_pipeline(ctx, min_stage_ms=0)
    assert not ctx.halt and ctx.is_scan and ctx.llm_calls == 0
    assert [f.code for f in ctx.findings if f.code.split(".")[0] in ("1", "2")] == ["1.2"]
    assert ctx.extraction["po_reference"] == "PO 105"
    from app.models import Invoice
    row = db.get(Invoice, ctx.run_id)
    assert row.total_paise == 78116000 and len(row.lines) == 2
    assert row.invoice_date.isoformat() == "2026-09-22"


def test_quotation_halts_with_1_4(db, no_network):
    ctx = create_run(db, (SAMPLES / "07_extra_quotation_acme.pdf").read_bytes(), "07.pdf")
    run_pipeline(ctx, min_stage_ms=0)
    assert ctx.halt
    assert [(f.code, f.severity, f.audience) for f in ctx.findings] == [("1.4", "reject", ["Vendor"])]


def test_tax_inclusive_back_calculation(db, tmp_cache, monkeypatch):
    ex = Extraction(doc_type="invoice", invoices=[ExtractedInvoice(
        total=118000.0, subtotal=118000.0, tax_inclusive=True,
        lines=[{"description": "Chair", "qty": 1, "unit_price": 118000.0, "tax_rate": 18.0, "amount": 118000.0}],
    )])
    monkeypatch.setattr(llm, "_call_model", lambda *a: ex)
    ctx = create_run(db, (SAMPLES / "01_happy_deccan.pdf").read_bytes(), "incl.pdf")
    run_pipeline(ctx, min_stage_ms=0)
    assert ctx.extraction["lines"][0]["amount"] == 100000.0
    assert ctx.extraction["subtotal"] == 100000.0
    assert "2.3" in [f.code for f in ctx.findings]


# --- fixtures agree with expected.json ----------------------------------------

@pytest.mark.parametrize("exp", EXPECTED, ids=[e["file"] for e in EXPECTED])
def test_fixture_matches_expected(exp):
    h = file_hash((SAMPLES / exp["file"]).read_bytes())
    cached = llm.load_cache(h)
    assert cached is not None, f"no fixture for {exp['file']}"
    inv = cached.invoices[0]
    assert inv.invoice_number == exp["invoice_no"]
    assert inv.invoice_date == exp["invoice_date"]
    assert inv.po_reference == exp["po_ref_printed"]
    # Sample 07 (quotation) prints only "Rs. 65,500 plus GST", so its total is null in both.
    assert (None if inv.total is None else rupees_to_paise(inv.total)) == exp["total_paise"]
