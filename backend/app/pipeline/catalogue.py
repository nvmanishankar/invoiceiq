"""Every case in the design doc (docs/InvoiceIQ_Solution_Design_PS1.md), described as the code handles it today.

Feeds the "How it works" page. tests/test_catalogue.py keeps it honest: every code a stage can raise is here as
Built, every Built case is raised by the code (or is the silent normal path), and every sample named here
really raises its case.

Fields:
- stage: the design doc's stage. `runs_in` is set when the check actually happens in a different stage.
- outcome: what the finding does to the decision (Pass / Hold / Reject / Info). `also`: a second outcome it can have.
- alerted: who gets an email, as the code routes it (Vendor / AP / Procurement / Finance).
- finding: False for the normal path, which passes without writing a finding.
- note: where today's behaviour differs from the design doc.
"""

from app import config

BUILT = "Built"
DESIGNED = "Designed, not built yet"

STAGES = [
    {"n": 1, "name": "Read document", "ai": False,
     "what": "Opens the PDF and works out whether it has real text or is a scanned picture."},
    {"n": 2, "name": "Extract fields", "ai": True,
     "what": "The AI reads the invoice once and fills in a fixed form: vendor, numbers, dates, lines, tax, bank account."},
    {"n": 3, "name": "Completeness and maths", "ai": False,
     "what": "Checks nothing essential is missing and that the numbers on the invoice add up."},
    {"n": 4, "name": "Verify vendor", "ai": False,
     "what": "Finds the vendor by their GST number and checks they're approved and being paid into the right account."},
    {"n": 5, "name": "Match PO", "ai": True,
     "what": "Finds the purchase order this invoice belongs to. The AI only compares item descriptions; rules pick the PO."},
    {"n": 6, "name": "Amounts and quantities", "ai": False,
     "what": "Compares prices, quantities and the total with what's left on the purchase order."},
    {"n": 7, "name": "Duplicates", "ai": False,
     "what": "Looks for the same invoice sent before, even with a reformatted number or as a new scan."},
    {"n": 8, "name": "Tax", "ai": False,
     "what": "Checks the GST: the right kind for the vendor's state, the right rate, and the right amount."},
    {"n": 9, "name": "Dates and terms", "ai": False,
     "what": "Works out when the invoice must be paid and flags invoices that are too old or already overdue."},
]


def _c(code, title, trigger, outcome, alerted=(), status=BUILT, sample=None, also=None, runs_in=None,
       finding=True, fraud=False, note=None):
    return {"code": code, "stage": int(code.split(".")[0]), "title": title, "trigger": trigger, "outcome": outcome,
            "also": also, "alerted": list(alerted), "status": status, "sample": sample, "runs_in": runs_in,
            "finding": finding if status == BUILT else False, "fraud": fraud, "note": note}


S01 = "01_happy_deccan.pdf"
S02 = "02_happy_brighttech_scan.pdf"
S03 = "03_edge_inferred_po_acme.pdf"
S04 = "04_edge_split_overbill_acme.pdf"
S05 = "05_edge_duplicate_sahyadri_scan.pdf"
S06 = "06_edge_bank_changed_brighttech.pdf"
S07 = "07_extra_quotation_acme.pdf"
S08 = "08_extra_wrong_split_brighttech.pdf"
S09 = "09_extra_missing_date_deccan.pdf"
S10 = "10_extra_blocked_quickfix.pdf"

_TOL = "the tolerance (2% capped at ₹5,000 by default, set in Settings)"

CASES = [
    # 1 Read document
    _c("1.1", "Clean text PDF", "The PDF has a real text layer, so it can be read directly.", "Pass",
       sample=S01, finding=False),
    _c("1.2", "Scanned invoice", "Almost no text on the page (under 50 characters a page), so it's treated as a "
       "picture and read visually.", "Info", sample=S02),
    _c("1.3", "File can't be opened", "The file is corrupt, password-protected or has no pages.", "Reject", ["AP"]),
    _c("1.4", "Not an invoice", "The AI says it's a quotation, purchase order, delivery note or statement.",
       "Reject", ["Vendor"], sample=S07, runs_in=2),
    _c("1.5", "Credit note", "The AI says the document is a credit note: money owed back, not a bill to pay.",
       "Hold", ["AP"], runs_in=2),
    _c("1.6", "Several invoices in one PDF", "The file holds more than one invoice with clear page boundaries.",
       "Hold", ["AP"], runs_in=2,
       note="Splitting into separate runs isn't built yet: the run holds and a person splits the file."),
    _c("1.7", "Unclear invoice boundaries", "The file seems to hold several invoices, but not where one ends.",
       "Hold", ["Vendor"], runs_in=2),
    # 2 Extract fields
    _c("2.1", "All fields clear", "The AI is confident about every key field.", "Pass", sample=S01, finding=False),
    _c("2.2", "Low-confidence reading", "The AI isn't sure about the invoice number, date, total, GSTIN, bank "
       "account or PO reference, or couldn't read the file at all.", "Hold", ["AP"]),
    _c("2.3", "Tax included in prices", "Prices are printed including GST, so the tax is taken out of each line "
       "before any check.", "Info"),
    # 3 Completeness and maths
    _c("3.1", "No invoice number", "The invoice number is missing.", "Hold", ["Vendor"]),
    _c("3.2", "No invoice date", "The date is missing or can't be read as a date.", "Hold", ["Vendor"], sample=S09),
    _c("3.3", "No total", "The total amount is missing.", "Hold", ["Vendor"]),
    _c("3.4", "Lines don't add up", "The line amounts add up to more than ₹1 away from the printed subtotal.",
       "Hold", ["Vendor"]),
    _c("3.5", "Subtotal + tax ≠ total", "Subtotal plus tax is more than ₹1 away from the printed total.",
       "Hold", ["Vendor"]),
    _c("3.6", "Dated in the future", "The invoice date is later than today.", "Hold", ["Vendor"]),
    _c("3.7", "Not itemised", "One line with no quantity, or no lines at all. Checked at total level only.", "Info"),
    # 4 Verify vendor
    _c("4.1", "Known, approved vendor", "The GSTIN is in the vendor list and the vendor is active.", "Pass",
       sample=S01),
    _c("4.2", "Name differs, GSTIN matches", "The printed name is spelled differently but the GSTIN matches. With no "
       "valid GSTIN, a close name match identifies the vendor instead.", "Pass", also="Info"),
    _c("4.3", "Invalid GSTIN", "The GST number has the wrong shape, an unknown state code or a bad check "
       "character.", "Hold", ["Vendor"]),
    _c("4.4", "Unknown vendor", "Neither the GSTIN nor the name matches any vendor we know.", "Hold",
       ["Procurement"]),
    _c("4.5", "Vendor blocked", "The vendor is marked Blocked in the vendor list.", "Reject", ["Procurement"],
       sample=S10),
    _c("4.6", "GSTIN doesn't match vendor", "The name matches a known vendor but the GSTIN isn't the one on file: "
       "possible impersonation.", "Hold", ["Finance", "AP"], fraud=True),
    _c("4.7", "Bank account changed", "The bank account on the invoice differs from the one on file: the classic "
       "payment fraud.", "Hold", ["Finance", "AP"], sample=S06, fraud=True),
    # 5 Match PO
    _c("5.1", "PO printed and found", "The PO number is printed exactly and belongs to this vendor.", "Pass",
       sample=S01),
    _c("5.2", "PO written differently", "The reference is written oddly ('PO 105', 'Ref 2026/105') and is "
       "tidied up to the real PO number.", "Pass", sample=S02),
    _c("5.3", "PO not found", "The printed PO number doesn't exist. If the vendor is known, the invoice's "
       "contents are used to suggest the likely PO.", "Hold", ["AP", "Vendor"], sample=S10),
    _c("5.4", "PO closed", "The PO is closed or cancelled, so nothing more can be paid against it.", "Hold",
       ["Procurement"]),
    _c("5.5", "PO belongs to another vendor", "The printed PO was issued to a different vendor.", "Hold",
       ["Vendor"]),
    _c("5.6", "Invoice dated before PO", "The invoice is dated before the PO was raised.", "Hold",
       ["Procurement", "AP"]),
    _c("5.7", "No PO, one clear winner", f"No usable reference, but one PO scores at least "
       f"{config.PO_MATCH_MIN_SCORE} and leads by {config.PO_MATCH_MIN_GAP} or more.", "Pass", sample=S03),
    _c("5.8", "Two POs fit", f"The best PO scores {config.PO_MATCH_MIN_SCORE}+ but leads the next by less than "
       f"{config.PO_MATCH_MIN_GAP}. A person picks.", "Hold", ["AP"]),
    _c("5.9", "No PO fits", f"No open PO for this vendor survives the filters, or the best scores under "
       f"{config.PO_MATCH_MIN_SCORE}.", "Hold", ["Vendor", "Procurement"], sample=S10),
    _c("5.10", "Spans two POs", "No single PO covers every line, but two together do.", "Hold", ["AP"]),
    _c("5.11", "Non-PO spend", "Rent, utilities or subscriptions that never have a PO; would go to a manager.",
       "Hold", ["AP"], status=DESIGNED),
    # 6 Amounts and quantities
    _c("6.1", "Exact match", "The total equals the PO total.", "Pass", sample=S01),
    _c("6.2", "Small difference", f"The total differs from the PO within {_TOL}.", "Pass"),
    _c("6.3", "Over PO amount", f"The total is more than the PO allows, beyond {_TOL}, on a PO not billed before.",
       "Hold", ["Vendor", "AP"]),
    _c("6.4", "Part-billing within balance", "Earlier invoices were approved on this PO and this one fits what's "
       "left.", "Pass"),
    _c("6.5", "Over PO balance", f"Earlier invoices used up part of the PO, and this one is more than what's left "
       f"plus {_TOL}.", "Hold", ["Vendor"], sample=S04),
    _c("6.6", "Quantity above ordered", "Quantities invoiced so far, plus this invoice, exceed what was ordered.",
       "Hold", ["Vendor"], sample=S04),
    _c("6.7", "Price above PO", f"A unit price is higher than the PO price by more than {_TOL}.", "Hold",
       ["Vendor"]),
    _c("6.8", "Item not on PO", "An invoice line matches nothing on the PO.", "Hold", ["Vendor", "Procurement"]),
    _c("6.9", "Under-billing", f"The total is under the PO by more than {_TOL}: a partial delivery. The rest "
       "stays open.", "Pass",
       sample=S03),
    # 7 Duplicates
    _c("7.1", "Same file again", "The exact same file was processed before.", "Reject", ["AP"], also="Hold",
       note="Reject if the first one was approved; Hold if it's still open."),
    _c("7.2", "Duplicate invoice", "Same vendor and invoice number (even written '42' instead of 'INV-0042'), "
       "plus the same amount or date.", "Reject", ["Vendor", "AP"], also="Hold", sample=S05,
       note="Reject if the first one was approved; Hold if it's still open."),
    _c("7.3", "Re-scanned copy", "Same vendor, amount and date under a different number.", "Reject",
       ["Vendor", "AP"], also="Hold", note="Reject if the first one was approved; Hold if it's still open."),
    _c("7.4", "Possible duplicate", f"Same vendor and amount, different number, dated within "
       f"{config.NEAR_DUPLICATE_DAYS} days.", "Hold", ["AP"]),
    _c("7.5", "Recurring invoice", "A genuine monthly bill: different number and billing period.", "Pass",
       status=DESIGNED,
       note=f"Billing periods aren't read yet. A same-amount bill within {config.NEAR_DUPLICATE_DAYS} days is "
            "held as a possible duplicate (7.4)."),
    # 8 Tax
    _c("8.1", "Same state: CGST + SGST", "Vendor and buyer are in the same state and GST is split in two equal "
       "halves.", "Pass", sample=S01),
    _c("8.2", "Other state: IGST", "Vendor and buyer are in different states and GST is charged as one IGST line.",
       "Pass", sample=S02),
    _c("8.3", "Wrong GST split", "The split doesn't fit the states, e.g. CGST + SGST from another state.", "Hold",
       ["Vendor"], sample=S08),
    _c("8.4", "Rate differs from PO", "A line's GST rate isn't the rate on the PO line.", "Hold", ["Vendor"]),
    _c("8.5", "Outdated rate", "The rate wasn't valid on the invoice date, e.g. 12% or 28% after 21 Sep 2025.",
       "Hold", ["Vendor"]),
    _c("8.6", "Tax amount wrong", "Line value × rate is more than ₹1 away from the tax shown, or CGST and SGST "
       "aren't equal halves.", "Hold", ["Vendor"]),
    _c("8.7", "Foreign vendor", "A vendor outside India charges GST. With no GST on the invoice it's just noted: "
       "tax is paid via customs or reverse charge.", "Hold", ["Vendor"], also="Info",
       note="The vendor hears only when GST was charged."),
    _c("8.8", "Buyer outside India", "The company isn't in India, so each line's rate is compared with the rate "
       "declared on the PO (not independently verified).", "Hold", ["Vendor"], also="Pass",
       note="Passes when every rate matches the PO; the vendor hears only about a mismatch."),
    # 9 Dates and terms
    _c("9.1", "Due date set", f"Due date = invoice date + the PO's payment terms ({config.DEFAULT_TERMS_DAYS} days if "
       "no PO matched).",
       "Pass", sample=S01),
    _c("9.2", "Invoice too old", f"The invoice is more than {config.STALE_INVOICE_DAYS} days old.", "Hold", ["AP"]),
    _c("9.3", "Terms differ from PO", "The invoice asks for different payment terms; the PO's terms apply.", "Info"),
    _c("9.4", "Overdue on arrival", "The due date has already passed: pay urgently.", "Info", ["AP"]),
    _c("9.5", "MSME vendor", f"The vendor is a small business (MSME), so the due date is capped at "
       f"{config.MSME_MAX_TERMS_DAYS} days by law.", "Info", sample=S01),
]

BY_CODE = {c["code"]: c for c in CASES}


def catalogue() -> dict:
    built = sum(c["status"] == BUILT for c in CASES)
    return {
        "counts": {"total": len(CASES), "built": built, "designed": len(CASES) - built},
        "stages": STAGES,
        "cases": CASES,
        "rules": {
            "po_match_min_score": config.PO_MATCH_MIN_SCORE,
            "po_match_min_gap": config.PO_MATCH_MIN_GAP,
            "po_weights": {"lines": config.PO_WEIGHT_LINES, "amount": config.PO_WEIGHT_AMOUNT,
                           "date": config.PO_WEIGHT_DATE},
            "max_llm_calls": config.MAX_LLM_CALLS_PER_RUN,
            "maths_tolerance_paise": config.MATHS_TOLERANCE_PAISE,
        },
    }
