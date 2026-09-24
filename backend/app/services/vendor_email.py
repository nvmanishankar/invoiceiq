"""The reviewer's 'Send to vendor' email: reason chips, a drafted note and the email itself, from templates (no LLM).

The chips are this run's vendor-facing hold/reject findings, one per case code, titled from cases.py. The note is drafted
from each finding's stored evidence, e.g. 6.5 → "Only ₹1,18,000 remains on PO-2026-101; please bill no more than that."
The reviewer can edit the note, and then the subject and body; the server checks what they send.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import alerts
from app.models import CompanySettings, Invoice, PoLine, RunStage
from app.pipeline.cases import case_title
from app.pipeline.runner import stored_finding
from app.tax.india_gst import SPLIT_LABEL
from app.utils.money import format_inr, format_qty

OTHER = "other"
SUBJECT_MAX = 200
BODY_MAX = 10_000
NOTE_MAX = 2_000


class EmailError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


# --- Findings -------------------------------------------------------------------------------------------------------

def vendor_findings(stages: list[RunStage]) -> list[dict]:
    """The findings the vendor can fix: holds and rejects addressed to the vendor, in stage order."""
    return [f for s in stages for f in (s.details or {}).get("findings", [])
            if "Vendor" in (f.get("audience") or []) and f.get("severity") in ("hold", "reject")]


def has_fraud(stages: list[RunStage]) -> bool:
    return any(f.get("fraud") for s in stages for f in (s.details or {}).get("findings", []))


# --- Note templates -------------------------------------------------------------------------------------------------

def _pct(r) -> str:
    return f"{r:g}%"


def _plural(unit: str | None, qty: float) -> str:
    if not unit:
        return "units" if qty != 1 else "unit"
    return unit if qty == 1 or unit.endswith("s") else f"{unit}s"


def _please(item: str | None, rest: str) -> str:
    """'A4 paper: please …' when the finding names a line, else 'Please …'."""
    return f"{item}: please {rest}" if item else f"Please {rest}"


def _po(e: dict, row: Invoice) -> str:
    return e.get("po_id") or row.po_id or "the PO"


def _gst_split(e: dict) -> str | None:
    expected, actual = e.get("expected_split"), e.get("actual_split")
    if not expected or not actual:
        return None
    rates = e.get("rates") or []
    if expected == "IGST":
        at = f" at {'/'.join(_pct(r) for r in rates)}" if rates else ""
        return f"Please reissue with IGST{at} instead of {SPLIT_LABEL.get(actual, actual)}."
    if expected == "CGST+SGST":
        half = "/".join(_pct(r / 2) for r in rates)
        at = f"CGST {half} + SGST {half}" if half else "CGST + SGST"
        return f"Please reissue with {at} instead of {SPLIT_LABEL.get(actual, actual)}."
    return f"Please reissue without GST instead of {SPLIT_LABEL.get(actual, actual)}."


def _qty_left(db: Session, e: dict, row: Invoice) -> str | None:
    ordered, already = e.get("ordered"), e.get("already")
    if ordered is None or already is None:
        return None
    left = max(ordered - already, 0)
    po = _po(e, row)
    item = e.get("po_line") or e.get("invoice_line") or "this item"
    line = db.scalar(select(PoLine).where(PoLine.po_id == row.po_id, PoLine.line_no == e.get("po_line_no"))) \
        if row.po_id and e.get("po_line_no") is not None else None
    if left == 0:
        return f"Nothing remains of {item} on {po}; please remove it from this invoice."
    unit = _plural(line.unit if line is not None else None, left)
    return f"Only {format_qty(left)} {unit} of {item} remain on {po}; please bill no more than that."


def note_line(db: Session, f: dict, row: Invoice) -> str | None:
    """One sentence telling the vendor what to change, or None when the finding's message says it already."""
    code, e = f["code"], f.get("evidence") or {}
    po = _po(e, row)
    if code == "1.4":
        return "Please send the invoice itself; the document we received isn't an invoice."
    if code == "1.7":
        return "Please send each invoice as its own PDF."
    if code == "3.1":
        return "Please add the invoice number."
    if code == "3.2":
        return "Please add the invoice date."
    if code == "3.3":
        return "Please add the invoice total."
    if code == "3.4":
        return "Please check the line amounts; they don't add up to the subtotal."
    if code == "3.5":
        return "Please check the totals; the subtotal plus tax doesn't equal the invoice total."
    if code == "3.6":
        return "Please correct the invoice date; it's in the future."
    if code == "4.3":
        return "Please check the GSTIN printed on the invoice."
    if code in ("5.3", "5.9"):
        return "Please add the PO number this invoice is for."
    if code == "5.5":
        return "Please bill against a PO issued to your company."
    if code in ("6.3", "6.5") and e.get("remaining_paise") is not None:
        return f"Only {format_inr(e['remaining_paise'])} remains on {po}; please bill no more than that."
    if code == "6.6":
        return _qty_left(db, e, row)
    if code == "6.7" and e.get("po_price_paise") is not None:
        return _please(e.get("invoice_line"), f"bill at the PO price of {format_inr(e['po_price_paise'])} per unit.")
    if code == "6.8" and e.get("invoice_line"):
        return f"Please remove '{e['invoice_line']}'; it isn't on {po}."
    if code == "7.2" or code == "7.3":
        prior = e.get("invoice_no")
        return f"This looks like invoice {prior}, which we already have; please don't send it again." if prior \
            else "We already have this invoice; please don't send it again."
    if code == "8.3":
        return _gst_split(e)
    if code == "8.4" and e.get("po_rate") is not None:
        return _please(e.get("line"), f"charge GST at {_pct(e['po_rate'])}, the rate on {po}.")
    if code == "8.5" and e.get("rate") is not None:
        return _please(e.get("line"), f"charge the GST rate valid on the invoice date; {_pct(e['rate'])} no longer "
                                      "applies.")
    if code == "8.6":
        if e.get("expected_tax_paise") is not None and f["message"].startswith("Tax should"):
            return f"Please correct the tax to {format_inr(e['expected_tax_paise'])}."
        return "Please split the tax into equal CGST and SGST halves."
    if code == "8.7":
        return "Please reissue without GST; for an overseas supplier we pay Indian tax through customs or reverse charge."
    return None


# --- Chips, draft, preview ------------------------------------------------------------------------------------------

def reason_chips(db: Session, row: Invoice, findings: list[dict]) -> list[dict]:
    """One chip per case code, in the order the findings were raised."""
    chips: dict[str, dict] = {}
    for f in findings:
        chip = chips.setdefault(f["code"], {"code": f["code"], "title": case_title(f["code"]), "messages": [],
                                            "suggestions": []})
        chip["messages"].append(f["message"])
        line = note_line(db, f, row)
        if line and line not in chip["suggestions"]:
            chip["suggestions"].append(line)
    return list(chips.values())


def draft_note(chips: list[dict], selected: list[str]) -> str:
    lines = [s for c in chips if c["code"] in selected for s in c["suggestions"]]
    return "\n".join(dict.fromkeys(lines))


def _selection(chips: list[dict], reasons: list[str] | None) -> list[str]:
    codes = [c["code"] for c in chips]
    if reasons is None:
        return codes or [OTHER]
    picked = [r.strip() for r in reasons if isinstance(r, str) and r.strip()]
    if not picked:
        raise EmailError(422, "Tick at least one reason.")
    unknown = [r for r in picked if r not in codes and r != OTHER]
    if unknown:
        raise EmailError(422, f"These reasons aren't on this invoice: {', '.join(unknown)}.")
    return [c for c in codes if c in picked] + ([OTHER] if OTHER in picked else [])


def reasons_text(chips: list[dict], selected: list[str]) -> str:
    titles = {c["code"]: c["title"] for c in chips}
    return ", ".join(titles.get(code, "Other") for code in selected)


def _compose(db: Session, row: Invoice, findings: list[dict], selected: list[str], note: str) -> tuple[str, str]:
    company = db.scalar(select(CompanySettings).limit(1))
    facts = alerts.Facts(row, company, row.vendor, row.po_id)
    chosen = [stored_finding(f) for f in findings if f["code"] in selected]
    # The link shows as a placeholder; the real one is made when the email is sent.
    body = alerts.vendor_body(facts, "Hold", chosen, None, note or None, link=alerts.pending_link())
    return alerts.subject("Vendor", facts, "Hold", False), body


def preview(db: Session, row: Invoice, stages: list[RunStage], reasons: list[str] | None = None,
            note: str | None = None) -> dict:
    """What the vendor would get. No reasons: every chip ticked and the drafted note."""
    if has_fraud(stages):
        raise EmailError(409, "This invoice has a fraud finding, so nothing goes to the vendor. Finance verifies it "
                              "by phone on the number on file.")
    findings = vendor_findings(stages)
    chips = reason_chips(db, row, findings)
    selected = _selection(chips, reasons)
    drafted = draft_note(chips, selected)
    note = drafted if note is None else note.strip()
    if len(note) > NOTE_MAX:
        raise EmailError(422, f"The note is longer than {NOTE_MAX:,} characters.")
    if OTHER in selected and not note:
        raise EmailError(422, "Please add a note telling the vendor what to fix.")
    subj, body = _compose(db, row, findings, selected, note)
    return {
        "run_id": row.run_id,
        "reasons": [{"code": c["code"], "title": c["title"], "messages": c["messages"], "suggestions": c["suggestions"]}
                    for c in chips],
        "selected": selected,
        "drafted_note": drafted,
        "note": note,
        "subject": subj,
        "body": body,
        "intended_for": f"{alerts.vendor_names(row.vendor, (row.extraction or {}).get('vendor_name'))[0]} (accounts)",
        "limits": {"subject": SUBJECT_MAX, "body": BODY_MAX, "note": NOTE_MAX},
    }


def final_email(db: Session, row: Invoice, stages: list[RunStage], reasons: list[str] | None, note: str | None,
                subject: str | None, body: str | None) -> dict:
    """Check what the reviewer is about to send, and record how it differs from the draft."""
    draft = preview(db, row, stages, reasons, note if note is not None else "")
    subject, body = (subject or "").strip(), (body or "").strip()
    if not subject:
        raise EmailError(422, "The email needs a subject.")
    if not body:
        raise EmailError(422, "The email needs a body.")
    if len(subject) > SUBJECT_MAX:
        raise EmailError(422, f"The subject is longer than {SUBJECT_MAX} characters.")
    if len(body) > BODY_MAX:
        raise EmailError(422, f"The email is longer than {BODY_MAX:,} characters.")
    return {
        "reasons": draft["selected"],
        "reasons_text": reasons_text(draft["reasons"], draft["selected"]),
        "note": draft["note"],
        "subject": subject,
        "body": body,
        "note_edited": draft["note"] != draft["drafted_note"],
        "email_edited": (subject, body) != (draft["subject"].strip(), draft["body"].strip()),
    }
