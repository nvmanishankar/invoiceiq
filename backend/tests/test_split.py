"""Case 1.6: one PDF with several invoices is split into child runs, each checked on its own (offline)."""

import io
import json

import pdfplumber
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import llm, seed
from app.config import BACKEND_DIR, settings
from app.db import SessionLocal
from app.main import app
from app.models import Alert, Invoice
from app.pipeline import split
from app.pipeline.runner import file_hash
from app.schemas import ExtractedInvoice, Extraction
from app.services import runs as run_service
from app.services import stats
from tests.helpers import TODAY

TWO = BACKEND_DIR / "tests" / "data" / "two_invoices.pdf"
TWO_BYTES = TWO.read_bytes()
FIXTURE = llm.load_cache(file_hash(TWO_BYTES))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "MIN_STAGE_MS", 0)
    monkeypatch.setattr(run_service, "today", lambda: TODAY)
    seed.reset()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def variant(monkeypatch):
    """A copy of two_invoices.pdf with a changed extraction: same pages, a different file (so its own cache entry)."""
    extra: dict[str, Extraction] = {}
    real = llm.load_cache

    def make(name: str, change) -> bytes:
        data = TWO_BYTES + f"\n%variant {name}\n".encode()
        ex = FIXTURE.model_copy(deep=True)
        change(ex)
        extra[file_hash(data)] = ex
        return data

    monkeypatch.setattr(llm, "load_cache", lambda h: extra[h].model_copy(deep=True) if h in extra else real(h))
    return make


def upload(client, data: bytes = TWO_BYTES, name: str = "two_invoices.pdf") -> str:
    r = client.post("/api/runs", files={"file": (name, data, "application/pdf")})
    assert r.status_code == 202, r.text
    return r.json()["run_id"]  # background tasks (the parent, then its children) have run when this returns


def detail(client, run_id: str) -> dict:
    r = client.get(f"/api/runs/{run_id}")
    assert r.status_code == 200, r.text
    return r.json()


def codes(run: dict) -> set[str]:
    return {f["code"] for f in run["findings"]}


def children(client, parent_id: str) -> list[dict]:
    parent = detail(client, parent_id)
    assert parent["status"] == split.SPLIT, parent["stages"]
    return [detail(client, c["run_id"]) for c in parent["split_children"]]


# --- The happy path -----------------------------------------------------------------------------------------------

def test_fixture_is_the_two_invoice_file():
    assert FIXTURE is not None and FIXTURE.doc_type == "invoice" and len(FIXTURE.invoices) == 2
    acme, deccan = FIXTURE.invoices
    assert (acme.invoice_number, acme.total, acme.po_reference, acme.page_range) == \
        ("ACME/2026/0417", 118000, "PO-2026-101", [1])
    assert (deccan.invoice_number, deccan.total, deccan.po_reference, deccan.page_range) == \
        ("DOI/2026-27/0171", 82600, "PO-2026-110", [2])


def test_two_invoices_split_into_two_approved_children(client):
    parent_id = upload(client)
    parent = detail(client, parent_id)
    assert parent["status"] == "split" and parent["decision"]["decision"] is None
    assert [s["name"] for s in parent["stages"]] == ["Read document", "Extract fields", "Decision"]
    kids = parent["split_children"]
    assert parent["stages"][-1]["message"] == f"Split into 2 invoices: {kids[0]['run_id']}, {kids[1]['run_id']}"
    assert parent["replaced_by"] is None and parent["split_from"] is None

    first, second = children(client, parent_id)
    assert (first["invoice_no"], first["decision"]["decision"], first["po_id"]) == \
        ("ACME/2026/0417", "Approve", "PO-2026-101")
    assert (second["invoice_no"], second["decision"]["decision"], second["po_id"]) == \
        ("DOI/2026-27/0171", "Approve", "PO-2026-110")
    for n, child in enumerate((first, second), start=1):
        assert child["parent_upload_id"] == parent_id
        assert child["split_from"] == {"run_id": parent_id, "pages": [n], "page_count": 2, "part": n, "parts": 2}
        read, fields = child["stages"][:2]
        assert (read["status"], fields["status"]) == ("pass", "pass")
        assert read["message"] == f"Split from {parent_id}, page {n} of 2"
        assert fields["message"].startswith(f"Split from {parent_id}, page {n} of 2")
        assert [s["order"] for s in child["stages"]] == list(range(1, 11))


def test_children_have_their_own_one_page_pdf(client):
    first, second = children(client, upload(client))
    for child, number in ((first, "ACME/2026/0417"), (second, "DOI/2026-27/0171")):
        r = client.get(f"/api/runs/{child['run_id']}/file")
        assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            assert len(pdf.pages) == 1 and number in pdf.pages[0].extract_text()


def test_parent_stream_ends_normally(client):
    parent_id = upload(client)
    events, event = [], None
    with client.stream("GET", f"/api/runs/{parent_id}/stream") as r:
        for line in r.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                events.append((event, json.loads(line[6:])))
    assert [k for k, _ in events] == ["stage", "stage", "stage", "decision", "done"]
    assert events[-2][1]["status"] == "split" and events[-2][1]["decision"] is None


def test_no_llm_calls_and_split_children_never_count_towards_the_cap(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_RUNS_PER_DAY", 1)
    parent_id = upload(client)
    parent = detail(client, parent_id)
    kids = children(client, parent_id)
    assert parent["stages"][1]["details"]["llm_calls"] == 0
    assert all(k["stages"][-1]["details"]["llm_calls"] == 0 for k in kids)
    assert all(k["decision"]["decision"] == "Approve" for k in kids)  # the cap didn't stop the children
    with SessionLocal() as db:
        assert run_service.runs_today(db) == 0  # a cached file: neither the upload nor its children count
        rows = db.scalars(select(Invoice).where(Invoice.parent_upload_id == parent_id)).all()
        assert [r.used_llm for r in rows] == [False, False]
    r = client.post("/api/runs", files={"file": ("again.pdf", TWO_BYTES, "application/pdf")})
    assert r.status_code == 202


def test_a_split_that_needed_the_ai_counts_once(client, variant, monkeypatch):
    data = variant("fresh", lambda ex: None)  # same invoices, but a file the AI had to read
    monkeypatch.setattr(run_service, "needs_llm", lambda h: True)
    monkeypatch.setattr("app.pipeline.runner.needs_llm", lambda h: True)
    parent_id = upload(client, data)
    assert len(children(client, parent_id)) == 2
    with SessionLocal() as db:
        assert run_service.runs_today(db) == 1


def test_children_never_call_the_llm_even_after_a_review(client, variant, monkeypatch):
    """A held child that a reviewer confirms is re-checked offline too (the conftest makes any model call fail)."""
    data = variant("no-date", lambda ex: setattr(ex.invoices[1], "invoice_date", None))
    _, held = children(client, upload(client, data))
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "key-that-must-not-be-used")
    r = client.post(f"/api/runs/{held['run_id']}/review", json={"action": "confirm",
                                                                "fields": {"invoice_date": "2026-09-21"}})
    assert r.status_code == 200, r.text
    after = detail(client, held["run_id"])
    assert after["decision"]["decision"] == "Approve"
    assert after["stages"][-1]["details"]["llm_calls"] == 0


# --- Page assignment ----------------------------------------------------------------------------------------------

def _invs(*ranges) -> list[ExtractedInvoice]:
    return [ExtractedInvoice(invoice_number=f"INV-{i}", page_range=list(r)) for i, r in enumerate(ranges, start=1)]


@pytest.mark.parametrize("ranges,pages,expected", [
    (([1], [2]), 2, [[1], [2]]),
    (([1, 2], [3]), 3, [[1, 2], [3]]),
    (([1, 3], [4]), 4, [[1, 2, 3], [4]]),  # [first, last]
    (([1], []), 2, None),  # missing
    (([1], [1, 2]), 2, None),  # overlapping
    (([1], [3]), 2, None),  # past the last page
    (([0], [1]), 1, None),  # not 1-based
    (([1], [3]), 3, None),  # page 2 belongs to nobody
    (([2, 1], [3]), 3, None),  # reversed
])
def test_pages_from_ranges(ranges, pages, expected):
    assert split.pages_from_ranges(_invs(*ranges), pages) == expected


def test_pages_from_text_needs_each_number_on_exactly_one_page():
    invs = _invs([], [])
    assert split.pages_from_text(invs, ["Invoice INV-2 ...", "Invoice INV-1 ..."]) == [[2], [1]]
    assert split.pages_from_text(invs, ["INV-1 and INV-2", "INV-2"]) is None  # INV-2 on both pages
    assert split.pages_from_text(invs, ["INV-1", ""]) is None  # INV-2 nowhere (e.g. a scan)
    assert split.pages_from_text(invs, ["INV-1", "INV-2", "terms"]) is None  # not one page each


@pytest.mark.parametrize("name,change", [
    ("missing", lambda ex: (setattr(ex.invoices[1], "page_range", []),
                            setattr(ex.invoices[1], "invoice_number", "DOI/2026-27/9999"))),
    ("overlapping", lambda ex: (setattr(ex.invoices[1], "page_range", [1, 2]),
                                setattr(ex.invoices[1], "invoice_number", "DOI/2026-27/9999"))),
    ("unclear", lambda ex: (setattr(ex, "boundaries_clear", False),
                            setattr(ex.invoices[0], "invoice_number", "ACME/2026/9999"))),
])
def test_pages_that_cant_be_assigned_hold_as_1_7(client, variant, name, change):
    run = detail(client, upload(client, variant(name, change)))
    assert run["status"] == "needs_review" and run["decision"]["decision"] == "Hold"
    assert codes(run) == {"1.7"}
    assert run["findings"][0]["audience"] == ["Vendor"]
    assert run["split_children"] is None
    with SessionLocal() as db:
        assert not db.scalars(select(Invoice).where(Invoice.parent_upload_id == run["run_id"])).all()


def test_one_page_each_fallback_when_the_ranges_are_missing(client, variant):
    def no_ranges(ex):
        for inv in ex.invoices:
            inv.page_range = []
    parent_id = upload(client, variant("no-ranges", no_ranges))
    first, second = children(client, parent_id)
    assert (first["invoice_no"], first["split_from"]["pages"]) == ("ACME/2026/0417", [1])
    assert (second["invoice_no"], second["split_from"]["pages"]) == ("DOI/2026-27/0171", [2])
    assert first["decision"]["decision"] == second["decision"]["decision"] == "Approve"


def test_children_run_in_page_order_whatever_the_extraction_order(client, variant):
    parent_id = upload(client, variant("reversed", lambda ex: ex.invoices.reverse()))
    first, second = children(client, parent_id)
    assert (first["invoice_no"], second["invoice_no"]) == ("ACME/2026/0417", "DOI/2026-27/0171")
    # One after another: the second child's checks start after the first child's decision.
    assert first["stages"][-1]["created_at"] <= second["stages"][2]["created_at"]


# --- Excluded from the queue, the dashboard and duplicates -------------------------------------------------------

def test_split_parent_is_not_in_the_queue_the_stats_or_the_duplicate_check(client, variant):
    data = variant("held", lambda ex: setattr(ex.invoices[1], "invoice_date", None))
    parent_id = upload(client, data)
    first, second = children(client, parent_id)

    queue = client.get("/api/review-queue").json()
    assert [r["run_id"] for r in queue["runs"]] == [second["run_id"]]

    with SessionLocal() as db:
        s = stats.compute(db)
    assert s["kpis"]["processed"] == 2 and s["kpis"]["in_progress"] == 0
    assert (s["kpis"]["approved"], s["kpis"]["held"]) == (1, 1)
    assert sum(d["Approve"] + d["Hold"] + d["Reject"] for d in s["series"]["decisions_per_day"]) == 2

    # The parent carries the children's invoice fields' file; the children aren't duplicates of it.
    assert not {"7.1", "7.2", "7.3", "7.4"} & (codes(first) | codes(second))
    with SessionLocal() as db:
        parent = db.get(Invoice, parent_id)
        parent.invoice_no, parent.total_paise, parent.vendor_id = "ACME/2026/0417", 11800000, "V-01"
        parent.decision = "Approve"  # even if it looked like an approved invoice, a split file is never compared
        db.commit()
    third, _ = children(client, upload(client, variant("again", lambda ex: None)))
    duplicates = next(s for s in third["stages"] if s["name"] == "Duplicates")
    assert parent_id not in duplicates["details"]["duplicate_of"]
    assert parent_id not in json.dumps(third["findings"])


def test_runs_list_filters_split_parents(client):
    parent_id = upload(client)
    rows = client.get("/api/runs", params={"status": "split"}).json()
    assert [r["run_id"] for r in rows] == [parent_id]


def test_uploading_the_same_file_again_rejects_both_children_as_duplicates(client):
    first_parent = upload(client)
    earlier = children(client, first_parent)
    again = children(client, upload(client))
    for old, new in zip(earlier, again):
        assert new["decision"]["decision"] == "Reject"
        assert "7.1" in codes(new), codes(new)  # the same pages give the same file; 7.2 isn't repeated for it
        assert any(f["code"] == "7.1" and old["run_id"] in f["message"] for f in new["findings"])
    assert all(detail(client, k["run_id"])["decision"]["decision"] == "Approve" for k in earlier)


# --- Mixed results --------------------------------------------------------------------------------------------------

def test_one_good_and_one_missing_date_approve_and_hold(client, variant):
    data = variant("missing-date", lambda ex: setattr(ex.invoices[1], "invoice_date", None))
    first, second = children(client, upload(client, data))
    assert first["decision"]["decision"] == "Approve"
    assert second["decision"]["decision"] == "Hold" and "3.2" in codes(second)
    assert "1.6" not in codes(first) | codes(second)


def _bank_changed(index: int):
    def change(ex):
        ex.invoices[index].bank_account = "99990000111122"
    return change


@pytest.mark.parametrize("bad", [1, 0], ids=["fraud-on-page-2", "fraud-on-page-1"])
def test_a_fraud_warning_holds_every_sibling_for_finance(client, variant, emails, bad):
    parent_id = upload(client, variant(f"bank-{bad}", _bank_changed(bad)))
    kids = children(client, parent_id)
    fraud, good = kids[bad], kids[1 - bad]

    assert fraud["decision"]["decision"] == "Hold" and "4.7" in codes(fraud)
    assert good["decision"]["decision"] == "Hold" and good["decision"]["fraud"] is True
    sibling = next(f for f in good["findings"] if f["code"] == "1.6")
    assert sibling["message"] == (f"Another invoice in the same file has a fraud warning ({fraud['run_id']}); "
                                  "Finance must verify both.")
    assert sibling["audience"] == ["Finance", "AP"] and sibling["fraud"] is True
    assert good["po_id"] in ("PO-2026-101", "PO-2026-110")  # every other check still ran and passed

    with SessionLocal() as db:
        for kid in kids:
            audiences = {a.audience for a in db.scalars(select(Alert).where(Alert.run_id == kid["run_id"]))}
            assert "Finance" in audiences and "Vendor" not in audiences, (kid["run_id"], audiences)
    assert emails, "Finance and AP were emailed"


def test_only_finance_can_clear_the_sibling_hold(client, variant):
    kids = children(client, upload(client, variant("bank-override", _bank_changed(1))))
    good = kids[0]
    r = client.post(f"/api/runs/{good['run_id']}/review", json={"action": "override", "reason": "looks fine"},
                    headers={"X-Role": "AP clerk"})
    assert r.status_code == 403
    r = client.post(f"/api/runs/{good['run_id']}/review", json={"action": "send_to_vendor", "reasons": ["1.6"]})
    assert r.status_code == 409


def test_a_held_sibling_that_would_be_rejected_stays_rejected(client, variant):
    def change(ex):
        _bank_changed(1)(ex)
        ex.invoices[0].vendor_gstin = "33AAQFQ1122B1ZS"  # Quickfix: blocked vendor → Reject, not turned into a Hold
        ex.invoices[0].vendor_name = "Quickfix Traders"
        ex.invoices[0].bank_account = "11223344556677"
    first, second = children(client, upload(client, variant("blocked", change)))
    assert first["decision"]["decision"] == "Reject" and "1.6" not in codes(first)
    assert second["decision"]["decision"] == "Hold"


def test_a_split_parent_cant_be_reviewed(client):
    parent_id = upload(client)
    r = client.post(f"/api/runs/{parent_id}/review", json={"action": "reject", "reason": "no"})
    assert r.status_code == 409


def test_cli_style_run_children_on_one_session(db):
    """runner.run_children: what the CLI uses, on a plain session."""
    from app.pipeline.runner import create_run, run_children, run_pipeline

    ctx = run_pipeline(create_run(db, TWO_BYTES, "two_invoices.pdf", today=TODAY, store_file=True), min_stage_ms=0)
    assert ctx.decision is None and len(ctx.children) == 2 and ctx.llm_calls == 0
    done = run_children(db, ctx.children, today=TODAY, min_stage_ms=0)
    assert [c.decision for c in done] == ["Approve", "Approve"]
    assert [c.po.po_id for c in done] == ["PO-2026-101", "PO-2026-110"]
    assert db.get(Invoice, ctx.run_id).status == "split"
