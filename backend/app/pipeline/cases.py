"""Short titles for the design doc's case codes, for charts and lists (docs/InvoiceIQ_Solution_Design_PS1.md)."""

from app.pipeline.context import SYSTEM_ERROR

CASE_TITLES = {
    "1.2": "Scanned invoice",
    "1.3": "File can't be opened",
    "1.4": "Not an invoice",
    "1.5": "Credit note",
    "1.6": "Several invoices in one PDF",
    "1.7": "Unclear invoice boundaries",
    "2.2": "Low-confidence reading",
    "2.3": "Tax included in prices",
    "3.1": "No invoice number",
    "3.2": "No invoice date",
    "3.3": "No total",
    "3.4": "Lines don't add up",
    "3.5": "Subtotal + tax ≠ total",
    "3.6": "Dated in the future",
    "3.7": "Not itemised",
    "4.3": "Invalid GSTIN",
    "4.4": "Unknown vendor",
    "4.5": "Vendor blocked",
    "4.6": "GSTIN doesn't match vendor",
    "4.7": "Bank account changed",
    "5.3": "PO not found",
    "5.4": "PO closed",
    "5.5": "PO belongs to another vendor",
    "5.6": "Invoice dated before PO",
    "5.8": "Two POs fit",
    "5.9": "No PO fits",
    "5.10": "Spans two POs",
    "6.3": "Over PO amount",
    "6.5": "Over PO balance",
    "6.6": "Quantity above ordered",
    "6.7": "Price above PO",
    "6.8": "Item not on PO",
    "7.1": "Same file again",
    "7.2": "Duplicate invoice",
    "7.3": "Re-scanned copy",
    "7.4": "Possible duplicate",
    "8.3": "Wrong GST split",
    "8.4": "Tax rate differs from PO",
    "8.5": "Outdated tax rate",
    "8.6": "Tax amount wrong",
    "8.7": "Foreign vendor charging tax",
    "9.2": "Invoice too old",
    SYSTEM_ERROR: "System error",
}


def case_title(code: str) -> str:
    return CASE_TITLES.get(code, code)
