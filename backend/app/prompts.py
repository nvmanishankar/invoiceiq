"""LLM prompts. The model reads; Python rules decide."""

EXTRACTION_PROMPT = """You extract data from vendor documents for an accounts payable team in India.
Return JSON that matches the schema exactly. Rules:
1. First classify doc_type. If it is not an invoice, still return what you can read.
2. If the file contains more than one invoice, return one entry per invoice with its page_range:
   the 1-based pages it is printed on, as [page] or [first_page, last_page].
   Set boundaries_clear=false if you are unsure where one ends.
3. Copy values exactly as printed. Never calculate, guess or fill in a missing value: use null.
4. po_reference: any purchase order reference anywhere on the page (header, notes, line text),
   exactly as written, e.g. "PO 105", "P.O. No: 2026/118". Null if none.
5. Amounts are numbers without currency symbols or commas. Dates in ISO format (yyyy-mm-dd).
6. If prices include tax (e.g. "incl. GST"), set tax_inclusive=true.
7. confidence: for invoice_number, invoice_date, total, vendor_gstin, bank_account, po_reference,
   say "low" if the text is blurry, partly hidden or ambiguous. Use null for a field that is absent.
Text layer (may be empty for scans):
<<<TEXT>>>"""

TEXT_LIMIT = 20000


def extraction_prompt(text: str) -> str:
    return EXTRACTION_PROMPT.replace("<<<TEXT>>>", (text or "")[:TEXT_LIMIT])


# Bump the version whenever the prompt changes, so cached scores are recomputed.
SIMILARITY_PROMPT_VERSION = "sim-v1"

SIMILARITY_PROMPT = """You compare item descriptions for an accounts payable team.
Each numbered pair has an item description from a vendor invoice (A) and a line from a
purchase order (B). For each pair, score from 0 to 1 how likely A and B describe the same
kind of item, so the invoice line could be billing that PO line:
- 1.0 the same item, possibly worded differently or with a brand name added
- about 0.5 related but a different item or specification (e.g. a different model or grade)
- 0.0 unrelated items
Judge only the item itself. Ignore quantities and prices. Return one score per pair.
Pairs:
<<<PAIRS>>>"""


def similarity_prompt(pairs: list[tuple[str, str]]) -> str:
    lines = [f'{i}. A: "{a}" | B: "{b}"' for i, (a, b) in enumerate(pairs)]
    return SIMILARITY_PROMPT.replace("<<<PAIRS>>>", "\n".join(lines))
