"""KPIs, chart series and health for the dashboard (build guide section 13).

Only real runs count: the seed ledger (is_seed) is history, not work InvoiceIQ did.
Three flat queries (runs, their stage rows, reviewed run ids), then plain Python, so a few hundred runs stay fast.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Invoice, Review, RunStage, Vendor
from app.pipeline.cases import case_title
from app.pipeline.context import SYSTEM_ERROR, code_label
from app.pipeline.runner import DECISION_ORDER
from app.utils.money import format_inr
from app.utils.timefmt import as_utc, iso

MINUTES_SAVED_PER_INVOICE = 8
DUPLICATE_CODES = {"7.1", "7.2", "7.3"}
OVERBILLING_CODES = {"6.3", "6.5"}
LOW_CONFIDENCE_CODE = "2.2"
AMOUNTS_STAGE = 6
EXTRACT_STAGE = 2
TOP_REASONS = 8
SUPERSEDED = "superseded"  # services.review.SUPERSEDED
SPLIT = "split"  # pipeline.split.SPLIT: a file of several invoices; its children are the runs that count


@dataclass
class RunFacts:
    run_id: str
    status: str
    decision: str | None
    total_paise: int | None
    created_at: datetime
    finished_at: datetime | None
    vendor_id: str | None
    vendor_name: str | None
    findings: list[dict] = field(default_factory=list)
    stage_ms: list[int] = field(default_factory=list)
    remaining_paise: int | None = None  # PO balance stage 6 checked against
    llm_calls: int | None = None
    reviewed: bool = False


def _load(db: Session) -> list[RunFacts]:
    rows = db.execute(
        select(Invoice.run_id, Invoice.status, Invoice.decision, Invoice.total_paise, Invoice.created_at,
               Invoice.finished_at, Invoice.vendor_id, Vendor.name)
        .outerjoin(Vendor, Vendor.vendor_id == Invoice.vendor_id)
        .where(Invoice.is_seed.is_(False), Invoice.status != SPLIT)
    ).all()
    runs = {r.run_id: RunFacts(*r) for r in rows}

    stages = db.execute(
        select(RunStage.run_id, RunStage.stage_order, RunStage.duration_ms, RunStage.details)
        .join(Invoice, Invoice.run_id == RunStage.run_id)
        .where(Invoice.is_seed.is_(False), Invoice.status != SPLIT)
    ).all()
    stage2_calls: dict[str, int] = {}
    for run_id, order, ms, details in stages:
        run = runs.get(run_id)
        if run is None:
            continue
        details = details or {}
        run.findings.extend(details.get("findings", []))
        if ms is not None:
            run.stage_ms.append(ms)
        if order == AMOUNTS_STAGE:
            run.remaining_paise = details.get("remaining_paise")
        elif order == EXTRACT_STAGE and details.get("llm_calls") is not None:
            stage2_calls[run_id] = details["llm_calls"]
        elif order == DECISION_ORDER and details.get("llm_calls") is not None:
            run.llm_calls = details["llm_calls"]
    for run_id, calls in stage2_calls.items():  # runs decided before the decision stage recorded it
        if runs[run_id].llm_calls is None:
            runs[run_id].llm_calls = calls

    reviewed = db.scalars(
        select(Review.run_id).join(Invoice, Invoice.run_id == Review.run_id)
        .where(Invoice.is_seed.is_(False)).distinct()
    ).all()
    for run_id in reviewed:
        if run_id in runs:
            runs[run_id].reviewed = True
    return list(runs.values())


def _codes(run: RunFacts) -> set[str]:
    return {f["code"] for f in run.findings}


def protected_paise(run: RunFacts) -> tuple[str, int] | None:
    """(category, paise) this run kept from being paid, counted once in its main category.

    Duplicates rejected and fraud holds protect the whole invoice; over-billing protects what's above the PO balance.
    An approved run protected nothing.
    """
    if run.decision in (None, "Approve") or run.total_paise is None:
        return None
    codes = _codes(run)
    if run.decision == "Reject" and codes & DUPLICATE_CODES:
        return "duplicates", run.total_paise
    if any(f.get("fraud") for f in run.findings):
        return "fraud", run.total_paise
    if codes & OVERBILLING_CODES and run.remaining_paise is not None:
        over = run.total_paise - max(run.remaining_paise, 0)
        if over > 0:
            return "overbilling", over
    return None


def _money(paise: int) -> dict:
    return {"paise": paise, "display": format_inr(paise)}


def _share(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def _local_day(v: datetime, offset: timedelta) -> date:
    return (as_utc(v) + offset).date()


def compute(db: Session, tz_offset_minutes: int = 0, days: int = 14, now: datetime | None = None) -> dict:
    """Everything the dashboard shows. `tz_offset_minutes` is the viewer's offset from UTC (IST = 330),
    so "today" and the per-day buckets match the viewer's calendar."""
    offset = timedelta(minutes=tz_offset_minutes)
    now = as_utc(now or datetime.now(timezone.utc))
    today = _local_day(now, offset)

    runs = _load(db)
    done = [r for r in runs if r.status != "running" and r.decision is not None]
    # A superseded run was replaced by a corrected invoice: its replacement carries the outcome, so it isn't counted
    # as a decision. What it blocked was still blocked, so it stays in money protected.
    live = [r for r in done if r.status != SUPERSEDED]
    processed = len(live)
    by_decision = Counter(r.decision for r in live)
    by_status = Counter(r.status for r in runs)
    touchless = sum(1 for r in live if r.decision == "Approve" and not r.reviewed)

    protected = {"duplicates": [0, 0], "overbilling": [0, 0], "fraud": [0, 0]}  # paise, runs
    for r in done:
        hit = protected_paise(r)
        if hit:
            protected[hit[0]][0] += hit[1]
            protected[hit[0]][1] += 1
    protected_total = sum(p for p, _ in protected.values())

    durations = [(as_utc(r.finished_at) - as_utc(r.created_at)).total_seconds() for r in done if r.finished_at]
    minutes_saved = processed * MINUTES_SAVED_PER_INVOICE

    # Decisions per day, oldest first, every day in the window present (empty days are zeros).
    first = today - timedelta(days=days - 1)
    per_day: dict[date, Counter] = {first + timedelta(days=i): Counter() for i in range(days)}
    for r in live:
        d = _local_day(r.created_at, offset)
        if d in per_day:
            per_day[d][r.decision] += 1

    # Hold / reject reasons: each code counted once per run.
    reason_runs: dict[str, Counter] = defaultdict(Counter)
    for r in live:
        if r.decision == "Approve":
            continue
        seen: dict[str, str] = {}
        for f in r.findings:
            if f.get("severity") in ("hold", "reject"):
                seen[f["code"]] = "reject" if f["severity"] == "reject" or seen.get(f["code"]) == "reject" else "hold"
        for code, sev in seen.items():
            reason_runs[code][sev] += 1
    reasons = sorted(
        ({"code": code, "label": code_label(code), "title": case_title(code), "count": c["hold"] + c["reject"],
          "hold": c["hold"], "reject": c["reject"]} for code, c in reason_runs.items()),
        key=lambda x: (-x["count"], x["code"]),
    )[:TOP_REASONS]

    stage_ms = [ms for r in done for ms in r.stage_ms]
    llm = [r.llm_calls for r in done if r.llm_calls is not None]
    low_conf = sum(1 for r in done if LOW_CONFIDENCE_CODE in _codes(r))
    sys_err = sum(1 for r in done if SYSTEM_ERROR in _codes(r))

    todays = [r for r in live if _local_day(r.created_at, offset) == today]
    vendors = Counter((r.vendor_id, r.vendor_name) for r in runs if r.vendor_id)

    return {
        "generated_at": iso(now),
        "kpis": {
            "processed": processed,
            "in_progress": by_status.get("running", 0),
            "touchless": touchless,
            "touchless_rate": _share(touchless, processed),
            "approved": by_decision.get("Approve", 0),
            "held": by_decision.get("Hold", 0),
            "rejected": by_decision.get("Reject", 0),
            "waiting_on_vendor": by_status.get("waiting_on_vendor", 0),
            "open_review": by_status.get("needs_review", 0),
            "superseded": by_status.get(SUPERSEDED, 0),
            "money_protected": {
                **_money(protected_total),
                "breakdown": [
                    {"key": "duplicates", "label": "Duplicates rejected", "runs": protected["duplicates"][1],
                     **_money(protected["duplicates"][0])},
                    {"key": "overbilling", "label": "Over-billing blocked", "runs": protected["overbilling"][1],
                     **_money(protected["overbilling"][0])},
                    {"key": "fraud", "label": "Fraud holds", "runs": protected["fraud"][1],
                     **_money(protected["fraud"][0])},
                ],
            },
            "time_saved": {
                "minutes": minutes_saved,
                "hours": round(minutes_saved / 60, 1),
                "minutes_per_invoice": MINUTES_SAVED_PER_INVOICE,
                "assumption": f"{MINUTES_SAVED_PER_INVOICE} minutes of manual AP work per invoice",
            },
            "avg_processing_seconds": round(sum(durations) / len(durations), 1) if durations else None,
        },
        "today": {
            "date": today.isoformat(),
            "processed": len(todays),
            "touchless": sum(1 for r in todays if r.decision == "Approve" and not r.reviewed),
            "held": sum(1 for r in todays if r.decision == "Hold"),
            "rejected": sum(1 for r in todays if r.decision == "Reject"),
        },
        "series": {
            "decisions_per_day": [
                {"date": d.isoformat(), "Approve": c["Approve"], "Hold": c["Hold"], "Reject": c["Reject"]}
                for d, c in per_day.items()
            ],
            "top_reasons": reasons,
        },
        "health": {
            "low_confidence_runs": low_conf,
            "low_confidence_share": _share(low_conf, processed),
            "system_error_runs": sys_err,
            "system_error_share": _share(sys_err, processed),
            "llm_calls_per_run": round(sum(llm) / len(llm), 2) if llm else None,
            "avg_stage_ms": round(sum(stage_ms) / len(stage_ms)) if stage_ms else None,
        },
        "vendors": [
            {"vendor_id": vid, "name": name or vid, "runs": n}
            for (vid, name), n in sorted(vendors.items(), key=lambda kv: (kv[0][1] or kv[0][0]))
        ],
    }
