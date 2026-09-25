"""The case catalogue must match the code: the "How it works" page is only as honest as this file."""

import ast
import re
from collections import defaultdict

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import seed
from app.config import BACKEND_DIR, REPO_DIR
from app.db import make_engine
from app.main import app
from app.pipeline.catalogue import BUILT, BY_CODE, CASES, DESIGNED, STAGES
from app.services import how_it_works
from app.services import runs as run_service
from tests.helpers import SAMPLES, TODAY, run_sample

SEVERITY = {"pass": "Pass", "hold": "Hold", "reject": "Reject", "info": "Info"}


def _const(node):
    return node.value if isinstance(node, ast.Constant) else None


def raised_by_code() -> dict[str, list[dict]]:
    """Every ctx.add(...) in the app, by code, read from the source."""
    found: dict[str, list[dict]] = defaultdict(list)
    for path in sorted((BACKEND_DIR / "app").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add"
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "ctx"):
                continue
            first = node.args[0]
            if isinstance(first, ast.Name) and first.id == "SYSTEM_ERROR":
                continue  # "System error" is a safety net, not a design-doc case
            code = _const(first)
            assert isinstance(code, str), f"{path.name}:{node.lineno}: finding code must be a literal string"
            audience = node.args[3] if len(node.args) > 3 else None
            fraud = next((_const(k.value) for k in node.keywords if k.arg == "fraud"), False)
            found[code].append({
                "where": f"{path.name}:{node.lineno}",
                "severity": _const(node.args[1]),
                "audience": [_const(e) for e in audience.elts] if isinstance(audience, ast.List) else None,
                "fraud": bool(fraud),
            })
    return found


RAISED = raised_by_code()


def test_every_design_doc_case_is_in_the_catalogue_once():
    doc = (REPO_DIR / "docs" / "InvoiceIQ_Solution_Design_PS1.md").read_text(encoding="utf-8")
    section = doc.split("## The invoice pipeline, case by case")[1].split("\n## ")[0]
    doc_codes = re.findall(r"^\| (\d+\.\d+) \|", section, flags=re.M)
    assert len(doc_codes) == 62
    assert [c["code"] for c in CASES] == doc_codes
    assert len(BY_CODE) == len(CASES)


def test_every_code_the_pipeline_raises_is_built():
    assert RAISED, "no ctx.add calls found"
    for code in RAISED:
        assert code in BY_CODE, f"{code} is raised by the code but missing from the catalogue"
        assert BY_CODE[code]["status"] == BUILT, f"{code} is raised by the code but marked {BY_CODE[code]['status']}"
        assert BY_CODE[code]["finding"], f"{code} is raised by the code but marked as writing no finding"


def test_nothing_marked_built_is_missing_from_the_code():
    for c in CASES:
        if c["status"] == BUILT and c["finding"]:
            assert c["code"] in RAISED, f"{c['code']} is marked Built but no stage raises it"
        if c["status"] == DESIGNED:
            assert c["code"] not in RAISED, f"{c['code']} is raised by the code but marked {DESIGNED}"
            assert not c["sample"]


def test_outcomes_audiences_and_fraud_match_the_code():
    for code, calls in RAISED.items():
        c = BY_CODE[code]
        allowed = {c["outcome"], c["also"]} - {None}
        for call in calls:
            if call["severity"] is not None:
                assert SEVERITY[call["severity"]] in allowed, f"{code} at {call['where']}: {call['severity']} vs {allowed}"
            else:
                assert c["also"], f"{code} at {call['where']} picks its severity at run time; catalogue needs `also`"
            if call["audience"] is not None:
                assert set(call["audience"]) <= set(c["alerted"]), f"{code} at {call['where']}: {call['audience']}"
            # An info note under a fraud case (4.7: no bank details on the invoice) isn't itself a fraud finding.
            assert call["fraud"] == c["fraud"] or call["severity"] == "info", \
                f"{code} at {call['where']}: fraud flag differs"
        audiences = set().union(*(set(call["audience"] or []) for call in calls))
        assert set(c["alerted"]) <= audiences, f"{code}: catalogue alerts {c['alerted']}, code alerts {audiences}"


def test_silent_cases_are_only_the_normal_path():
    silent = {c["code"] for c in CASES if c["status"] == BUILT and not c["finding"]}
    assert silent == {"1.1", "2.1"}


def test_stages_and_ai_badges():
    assert [s["n"] for s in STAGES] == list(range(1, 10))
    assert {s["n"] for s in STAGES if s["ai"]} == {2, 5}
    for c in CASES:
        assert c["outcome"] in SEVERITY.values() and c["title"] and c["trigger"]


def _codes_for(sample: str) -> set[str]:
    engine = make_engine("sqlite://")
    seed.reset(engine)
    try:
        with Session(engine) as db:
            return set(run_sample(db, sample).codes())
    finally:
        engine.dispose()


def test_every_try_it_sample_really_shows_its_case():
    by_sample = defaultdict(list)
    for c in CASES:
        if c["sample"]:
            assert (SAMPLES / c["sample"]).is_file(), c["sample"]
            by_sample[c["sample"]].append(c)
    for sample, cases in by_sample.items():
        codes = _codes_for(sample)
        for c in cases:
            if c["finding"]:
                assert c["code"] in codes, f"{c['code']}: {sample} raised {sorted(codes)}"
            else:  # the silent normal path: that stage raised nothing at all
                assert not any(x.startswith(f"{c['stage']}.") for x in codes), f"{c['code']}: {sample} raised {sorted(codes)}"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(run_service, "today", lambda: TODAY)
    how_it_works._walkthrough.cache_clear()
    seed.reset()
    with TestClient(app) as c:
        yield c
    how_it_works._walkthrough.cache_clear()


def test_cases_endpoint(client):
    r = client.get("/api/how-it-works/cases")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"] == {"total": 62, "built": sum(c["status"] == BUILT for c in CASES),
                              "designed": sum(c["status"] == DESIGNED for c in CASES)}
    assert len(body["cases"]) == 62 and len(body["stages"]) == 9
    assert body["rules"]["po_match_min_score"] == 70 and body["rules"]["po_match_min_gap"] == 20


def test_po_walkthrough_endpoint_runs_the_real_pipeline(client):
    r = client.get("/api/how-it-works/po-walkthrough")
    assert r.status_code == 200
    w = r.json()
    assert w["matched_po"] == "PO-2026-104" and w["match_type"] == "Inferred" and w["decision"] == "Approve"
    survivors = [e["po_id"] for e in w["elimination"] if e["eliminated_by"] is None]
    assert sorted(survivors) == sorted(s["po_id"] for s in w["scores"])
    top, second = w["scores"][0], w["scores"][1]
    assert top["po_id"] == "PO-2026-104"
    assert top["total"] >= 70 and top["total"] - second["total"] >= 20
    assert all(e["po"] for e in w["elimination"])


def test_tax_rates_endpoint_includes_ended_slabs(client):
    rates = client.get("/api/how-it-works/tax-rates").json()
    ended = {r["rate"]: r["valid_to"] for r in rates if r["valid_to"]}
    assert ended == {12: "2025-09-21", 28: "2025-09-21"}
