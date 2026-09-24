"""Text normalisation: invoice numbers, PO references, currency, names (build guide section 9)."""

import re

_INR_FORMS = {"RS", "RS.", "INR", "₹", "RUPEES", "RUPEE"}
_LEGAL_SUFFIXES = {"private", "pvt", "limited", "ltd", "llp", "co", "company", "inc", "the"}


def norm_full(inv_no: str | None) -> str:
    """'SPH/INV-0042' → 'SPHINV0042'."""
    return re.sub(r"[^A-Z0-9]", "", (inv_no or "").upper())


def core_number(inv_no: str | None) -> str | None:
    """Last digit group without leading zeros: 'SPH/INV-0042' → '42', '42' → '42'."""
    groups = re.findall(r"\d+", inv_no or "")
    return str(int(groups[-1])) if groups else None


def po_candidates_from_ref(raw: str | None, invoice_year: int) -> list[str]:
    """PO ids a printed reference could mean, most likely first.

    'PO-2026-118', 'P.O. No: 2026/118' → ['PO-2026-118']; 'PO 105' → ['PO-2026-105', 'PO-2025-105'].
    """
    nums = re.findall(r"\d+", raw or "")
    if len(nums) >= 2 and len(nums[-2]) == 4:
        return [f"PO-{nums[-2]}-{int(nums[-1]):03d}"]
    if len(nums) == 1:
        n = int(nums[0])
        return [f"PO-{invoice_year}-{n:03d}", f"PO-{invoice_year - 1}-{n:03d}"]
    return []


def normalise_currency(raw: str | None) -> str | None:
    """'Rs.', 'Rs', 'INR', '₹' → 'INR'; other ISO codes upper-cased; None stays None."""
    if raw is None:
        return None
    s = raw.strip()
    if s.upper() in _INR_FORMS or s.upper().rstrip(".") in _INR_FORMS:
        return "INR"
    if re.fullmatch(r"[A-Za-z]{3}", s):
        return s.upper()
    return s or None


def text_key(s: str | None) -> str:
    """Lower-case words and numbers only, for 'is this the same text' checks."""
    return " ".join(re.findall(r"[a-z0-9]+", (s or "").lower()))


def company_name_key(name: str | None) -> str:
    """Name without legal suffixes: 'BrightTech Solutions Pvt Ltd' → 'brighttech solutions'."""
    return " ".join(w for w in text_key(name).split() if w not in _LEGAL_SUFFIXES)


def digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")
