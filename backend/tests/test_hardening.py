"""Pilot hardening: PO lock at approval, grounding, bank details, masking and the vendor-link rate limit (offline)."""

import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import llm, seed
from app.config import settings
from app.db import make_engine
from app.main import app
from app.pipeline import runner
from app.pipeline.runner import create_run, file_hash, run_pipeline
from app.pipeline.s2_extract import grounding_key, ungrounded
from app.schemas import ExtractedInvoice
from app.services import runs as run_service
from app.services.views import mask_account, mask_bank
from app.utils.ratelimit import RateLimiter
from tests.helpers import SAMPLES, TODAY, finding, run_rules, sample_extraction
from tests.test_split import TWO_BYTES, variant  # noqa: F401  (fixture)

HAPPY = "01_happy_deccan.pdf"  # PO-2026-109: 10 desks at ₹18,000 and 10 pedestals at ₹4,500, ₹2,65,500 with GST
FRAUD = "06_edge_bank_changed_brighttech.pdf"  # invoice account ends 7766, file ends 5667
SCAN = "02_happy_brighttech_scan.pdf"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "MIN_STAGE_MS", 0)
    monkeypatch.setattr(run_service, "today", lambda: TODAY)
    seed.reset()
    with TestClient(app) as c:
        yield c


def part_invoice(number: str, desks: int, pedestals: int, day: int) -> dict:
    """A part-bill of sample 01's PO. Each fits PO-2026-109 alone; 6+5 desks together don't (10 ordered)."""
    ex = sample_extraction(HAPPY)
    ex["invoice_number"], ex["invoice_date"] = number, f"2026-09-{day:02d}"
    ex["lines"][0].update(qty=float(desks), amount=18000.0 * desks)
    ex["lines"][1].update(qty=float(pedestals), amount=4500.0 * pedestals)
    sub = 18000.0 * desks + 4500.0 * pedestals
    ex.update(subtotal=sub, cgst=round(sub * 0.09, 2), sgst=round(sub * 0.09, 2), total=round(sub * 1.18, 2))
    return ex


def run_part(db, ex: dict, name: str = "part.pdf"):
    """Stages 3-9 and the decision, with the invoice row written as stage 2 would (the PO ledger reads it)."""
    from app.models import Invoice
    from app.pipeline.s2_extract import write_invoice_row
    ctx = create_run(db, f"%PDF-part-{ex['invoice_number']}".encode(), name, today=TODAY)
    ctx.extraction = ex
    write_invoice_row(db.get(Invoice, ctx.run_id), "invoice", ex, ExtractedInvoice.model_validate(ex))
    db.commit()
    return run_pipeline(ctx, start_at=2, min_stage_ms=0)


A = ("DOI/2026-27/0201", 6, 6, 20)  # ₹1,59,300
B = ("DOI/2026-27/0202", 5, 5, 21)  # ₹1,32,750; with A ₹2,92,050 of ₹2,65,500 and 11 of 10 desks


def test_each_part_bill_fits_on_its_own(db):
    for inv in (A, B):
        engine = make_engine("sqlite://")
        seed.reset(engine)
        with Session(engine) as s:
            ctx = run_part(s, part_invoice(*inv))
            assert ctx.decision == "Approve", ctx.codes()
        engine.dispose()


# --- 1. PO balance at approval ----------------------------------------------------------------------------------------

def _stages_with_pause(pause):
    """The pipeline with `pause()` called after the last check, just before the decision."""
    name, fn = runner.STAGES[-1]

    def last(ctx):
        result = fn(ctx)
        pause(ctx)
        return result

    return [*runner.STAGES[:-1], (name, last)]


def test_approval_made_meanwhile_turns_the_second_into_a_hold(db, monkeypatch):
    """Deterministic: while B sits between its checks and its decision, A is approved against the same PO."""
    def approve_a(ctx):
        if ctx.inv.invoice_no == B[0]:
            with Session(db.get_bind()) as other:
                assert run_part(other, part_invoice(*A)).decision == "Approve"

    monkeypatch.setattr(runner, "STAGES", _stages_with_pause(approve_a))
    b = run_part(db, part_invoice(*B))
    assert b.decision == "Hold"
    stage6 = next(f for f in b.findings if f.code == "6.6")  # stage 6 itself passed: this is the recheck
    assert "11 invoiced in total vs 10 ordered on PO-2026-109" in stage6.message
    over = finding(b, "6.5")
    assert "approved while this one was being checked" in over.message
    assert over.evidence["remaining_paise"] == 26_550_000 - 15_930_000
    assert b.findings.index(over) > len(b.findings) - 4  # raised by the decision step, after every stage


def test_postgres_locks_the_po_row_for_update():
    from sqlalchemy.dialects import postgresql

    from app.services.po import lock_po

    class FakeSession:
        statements = []

        def get_bind(self):
            return type("Bind", (), {"dialect": postgresql.dialect()})()

        def execute(self, stmt):
            self.statements.append(str(stmt.compile(dialect=postgresql.dialect())))

    db = FakeSession()
    lock_po(db, "PO-2026-101")
    assert db.statements and db.statements[0].rstrip().endswith("FOR UPDATE")
    assert "purchase_orders.po_id = " in db.statements[0]


def test_two_runs_racing_for_one_po_only_one_is_approved(tmp_path, monkeypatch):
    """Real concurrency: two threads, two connections to one SQLite file, both past stage 6 before either decides."""
    engine = make_engine(f"sqlite:///{tmp_path / 'race.db'}")
    seed.reset(engine)
    barrier = threading.Barrier(2, timeout=20)
    monkeypatch.setattr(runner, "STAGES", _stages_with_pause(lambda ctx: barrier.wait()))
    results, errors = {}, []

    def go(inv):
        try:
            with Session(engine) as s:
                ctx = run_part(s, part_invoice(*inv), "race.pdf")
                results[inv[0]] = (ctx.decision, ctx.codes())
        except Exception as e:  # pragma: no cover - reported below
            errors.append(e)

    threads = [threading.Thread(target=go, args=(inv,)) for inv in (A, B)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    engine.dispose()
    assert not errors, errors
    decisions = sorted(d for d, _ in results.values())
    assert decisions == ["Approve", "Hold"], results
    held = next(codes for d, codes in results.values() if d == "Hold")
    assert "6.5" in held or "6.6" in held
    assert "sys" not in held  # held by the rule, not by a lock timeout


# --- 3. Grounding -----------------------------------------------------------------------------------------------------

@pytest.fixture
def cached(monkeypatch):
    """Replace the cached reading of a sample with a changed one (as a model's mistake would be)."""
    real = llm.load_cache

    def use(name: str, change) -> bytes:
        data = (SAMPLES / name).read_bytes()
        ex = real(file_hash(data)).model_copy(deep=True)
        change(ex.invoices[0])
        monkeypatch.setattr(llm, "load_cache", lambda h: ex.model_copy(deep=True) if h == file_hash(data) else real(h))
        return data

    return use


def _run_bytes(db, data: bytes, name: str):
    return run_pipeline(create_run(db, data, name, today=TODAY), min_stage_ms=0)


def test_grounding_key_normalises_amounts_and_numbers():
    assert grounding_key("₹ 1,41,600.00") == grounding_key("141600") == grounding_key("Rs. 141600.00") == "141600"
    assert grounding_key("INR 1,41,600.50") == "141600.50"
    assert grounding_key("ACME / 2026 / 0417") == "acme/2026/0417"
    inv = ExtractedInvoice(invoice_number="acme/2026/0417", total=141600.0, vendor_gstin="36aabca1234f1za")
    assert ungrounded(inv, "Invoice No: ACME/2026/0417  GSTIN 36AABCA1234F1ZA  Total ₹1,41,600.00") == []
    assert ungrounded(inv, "Invoice No: ACME/2026/0417  Total ₹1,41,000.00") == ["vendor_gstin", "total"]


def test_hallucinated_total_is_held_for_confirmation(db, cached):
    data = cached(HAPPY, lambda inv: setattr(inv, "total", 256500.0))  # digits swapped: not on the page
    ctx = _run_bytes(db, data, HAPPY)
    assert ctx.decision == "Hold"
    f = next(f for f in ctx.findings if f.code == "2.2")
    assert f.message == "Couldn't find total '₹2,56,500' in the document; please confirm."
    assert f.severity == "hold" and f.audience == ["AP"]
    assert ctx.extraction["confidence"]["total"] == "low"  # the review form flags it
    assert ctx.extraction["confidence"]["invoice_number"] == "high"


def test_hallucinated_bank_account_is_held_for_confirmation(db, cached):
    data = cached(HAPPY, lambda inv: setattr(inv, "bank_account", "61234567899999"))
    ctx = _run_bytes(db, data, HAPPY)
    assert ctx.decision == "Hold"
    msgs = [f.message for f in ctx.findings if f.code == "2.2"]
    assert msgs == ["Couldn't find bank account '61234567899999' in the document; please confirm."]
    assert ctx.extraction["confidence"]["bank_account"] == "low"
    assert "4.7" in ctx.codes()  # and it isn't the account on file either


def test_values_printed_differently_are_found(db, cached):
    """1,41,600.00 on the page and 141600 from the model are the same; so are case and spacing."""
    data = cached(HAPPY, lambda inv: setattr(inv, "invoice_number", "doi/2026-27/0158"))
    ctx = _run_bytes(db, data, HAPPY)
    assert ctx.decision == "Approve", ctx.codes()
    assert "2.2" not in ctx.codes()


def test_scans_are_not_grounded(db, cached):
    data = cached(SCAN, lambda inv: setattr(inv, "invoice_number", "BT/26/0874-X"))
    ctx = _run_bytes(db, data, SCAN)
    assert "2.2" not in ctx.codes()
    from app.models import RunStage
    stage2 = db.query(RunStage).filter_by(run_id=ctx.run_id, stage_order=2).one()
    assert stage2.details["grounding"] == {"checked": False, "note": "not checked: scanned"}


def test_split_children_are_grounded_on_their_own_pages(client, variant):  # noqa: F811
    """Invoice 2 claiming invoice 1's number: that number is in the file, but not on invoice 2's page."""
    from tests.test_split import children, upload
    data = variant("borrowed-number", lambda ex: setattr(ex.invoices[1], "invoice_number", "ACME/2026/0417"))
    first, second = children(client, upload(client, data))
    assert first["decision"]["decision"] == "Approve"
    assert second["decision"]["decision"] == "Hold"
    assert any(f["code"] == "2.2" and "invoice number 'ACME/2026/0417'" in f["message"] for f in second["findings"])
    assert second["extraction"]["confidence"]["invoice_number"] == "low"


def test_every_sample_is_grounded(db):
    """All 10 samples: every text PDF's fields are on its page, so none gains a grounding hold."""
    from tests.helpers import EXPECTED, run_sample
    for e in EXPECTED:
        ctx = run_sample(db, e["file"])
        assert ctx.decision == e["decision"], (e["file"], ctx.codes())
        assert not [f for f in ctx.findings if f.code == "2.2" and "Couldn't find" in f.message], e["file"]


# --- 4. Bank details --------------------------------------------------------------------------------------------------

def test_same_account_different_ifsc_is_a_fraud_hold(db):
    ex = sample_extraction(HAPPY)
    ex["ifsc"] = "HDFC0009999"  # the account number is the one on file; the bank isn't
    ctx = run_rules(db, ex)
    f = finding(ctx, "4.7")
    assert ctx.decision == "Hold" and f.fraud and f.severity == "hold" and f.audience == ["Finance", "AP"]
    assert "IFSC on the invoice (HDFC0009999) differs from the one on file (ICIC0001122)" in f.message


def test_ifsc_is_compared_only_when_both_are_given(db):
    ex = sample_extraction(HAPPY)
    ex["ifsc"] = None
    assert run_rules(db, ex).decision == "Approve"


def test_ifsc_formatting_doesnt_count_as_a_change(db):
    ex = sample_extraction(HAPPY)
    ex["ifsc"] = "icic 0001122"
    assert run_rules(db, ex).decision == "Approve"


def test_no_bank_details_is_an_info_note(db):
    ex = sample_extraction(HAPPY)
    ex["bank_account"], ex["ifsc"] = None, None
    ctx = run_rules(db, ex)
    f = finding(ctx, "4.7")
    assert ctx.decision == "Approve"
    assert f.severity == "info" and not f.fraud and f.audience == []
    assert f.message == "No bank details on the invoice; payment goes to the account on file."


# --- 6. Masking -------------------------------------------------------------------------------------------------------

def _run_sample(client, name: str) -> str:
    r = client.post("/api/runs", json={"sample_name": name})
    assert r.status_code == 202, r.text
    return r.json()["run_id"]


def _get(client, run_id: str, role: str | None = None) -> dict:
    return client.get(f"/api/runs/{run_id}", headers={"X-Role": role} if role else {}).json()


def test_mask_helpers():
    assert mask_account("5020 0099 887766") == "…7766"
    assert mask_account(None) is None and mask_account("") == ""
    out = mask_bank({"a": [{"bank_account": "50200099887766"}],
                     "bank_account": {"label": "Bank account", "before": "111122223333", "after": "999988887777"}})
    assert out == {"a": [{"bank_account": "…7766"}],
                   "bank_account": {"label": "Bank account", "before": "…3333", "after": "…7777"}}


@pytest.mark.parametrize("role", [None, "AP clerk", "Procurement"])
def test_fraud_run_is_masked_for_everyone_but_finance(client, role):
    run_id = _run_sample(client, FRAUD)
    d = _get(client, run_id, role)
    assert d["invoice"]["bank_account"] == "…7766"
    assert d["vendor"]["bank_account_on_file"] == "…5667"
    assert d["extraction"]["bank_account"] == "…7766"
    assert d["stages"][1]["details"]["fields"]["bank_account"] == "…7766"
    raw = client.get(f"/api/runs/{run_id}", headers={"X-Role": role} if role else {}).text
    assert "50200099887766" not in raw and "91201004455667" not in raw


def test_finance_sees_full_numbers_on_a_fraud_hold(client):
    run_id = _run_sample(client, FRAUD)
    d = _get(client, run_id, "Finance")
    assert d["invoice"]["bank_account"] == "50200099887766"
    assert d["vendor"]["bank_account_on_file"] == "91201004455667"
    assert d["extraction"]["bank_account"] == "50200099887766"
    # Once cleared, it isn't a fraud hold any more: masked again, for Finance too.
    r = client.post(f"/api/runs/{run_id}/review", headers={"X-Role": "Finance"},
                    json={"action": "override", "reason": "Called on file number; change confirmed"})
    assert r.status_code == 200, r.text
    assert _get(client, run_id, "Finance")["invoice"]["bank_account"] == "…7766"


def test_finance_sees_masked_numbers_on_other_runs(client):
    run_id = _run_sample(client, HAPPY)
    d = _get(client, run_id, "Finance")
    assert d["invoice"]["bank_account"] == "…0123" and d["vendor"]["bank_account_on_file"] == "…0123"


def test_stream_and_lists_are_masked(client):
    run_id = _run_sample(client, FRAUD)
    with client.stream("GET", f"/api/runs/{run_id}/stream") as r:
        body = "".join(r.iter_text())
    assert "…7766" in body and "50200099887766" not in body
    vendors = client.get("/api/vendors").text
    assert "91201004455667" not in vendors and "…5667" in vendors
    for path in ("/api/runs", "/api/review-queue", "/api/alerts", "/api/pos"):
        assert "50200099887766" not in client.get(path).text, path


def test_a_masked_account_cant_be_saved_back(client):
    run_id = _run_sample(client, "09_extra_missing_date_deccan.pdf")
    r = client.post(f"/api/runs/{run_id}/review",
                    json={"action": "confirm", "fields": {"invoice_date": "2026-09-20", "bank_account": "…0123"}})
    assert r.status_code == 422 and "masked" in r.json()["detail"]


# --- 7. Vendor link rate limit ----------------------------------------------------------------------------------------

def test_rate_limiter_window():
    now = [0.0]
    rl = RateLimiter(2, 60, clock=lambda: now[0])
    rl.hit("k"), rl.hit("k")
    assert rl.retry_after("k") == 60 and rl.retry_after("other") == 0
    now[0] = 30
    assert rl.retry_after("k") == 30
    now[0] = 60.5
    assert rl.retry_after("k") == 0


def _post(client, token: str, ip: str = "testclient"):
    return client.post(f"/api/respond/{token}", files={"file": ("x.pdf", b"%PDF-1.4 x", "application/pdf")})


def test_five_uploads_per_link_an_hour(client):
    for _ in range(5):
        assert _post(client, "some-token").status_code == 404  # unknown link, but each try counts
    r = _post(client, "some-token")
    assert r.status_code == 429 and r.json()["state"] == "busy"
    assert 3500 <= int(r.headers["Retry-After"]) <= 3600
    assert _post(client, "another-token").status_code == 404  # other links aren't affected


def test_twenty_uploads_per_address_an_hour(client):
    for i in range(20):
        assert _post(client, f"token-{i}").status_code == 404
    r = _post(client, "token-new")
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    assert client.get("/api/respond/token-new").status_code == 404  # only uploads are limited
