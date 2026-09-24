"""Shared helpers: run samples or hand-made extractions through the pipeline, offline."""

import copy
import json
import uuid
from datetime import date

from app import llm
from app.config import BACKEND_DIR
from app.pipeline.runner import create_run, file_hash, run_pipeline

SAMPLES = BACKEND_DIR / "samples"
EXPECTED = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))
TODAY = date(2026, 9, 24)  # pinned so date rules (future, stale, overdue) don't drift


def run_sample(db, name: str, today: date = TODAY):
    ctx = create_run(db, (SAMPLES / name).read_bytes(), name, today=today)
    return run_pipeline(ctx, min_stage_ms=0)


def sample_extraction(name: str) -> dict:
    """The committed extraction fixture for a sample, as a dict you can change."""
    cached = llm.load_cache(file_hash((SAMPLES / name).read_bytes()))
    return copy.deepcopy(cached.invoices[0].model_dump(mode="json"))


def run_rules(db, extraction: dict, today: date = TODAY):
    """Stages 3-9 and the decision on a hand-made extraction (stages 1-2 skipped)."""
    ctx = create_run(db, f"%PDF-test-{uuid.uuid4()}".encode(), "test.pdf", today=today)
    ctx.extraction = extraction
    return run_pipeline(ctx, start_at=2, min_stage_ms=0)


def finding(ctx, code: str):
    found = [f for f in ctx.findings if f.code == code]
    assert found, f"{code} not in {ctx.codes()}"
    return found[0]
