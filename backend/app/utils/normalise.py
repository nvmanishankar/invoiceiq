"""Text normalisation for invoice numbers (build guide section 9, stage 7)."""

import re


def norm_full(inv_no: str | None) -> str:
    """'SPH/INV-0042' → 'SPHINV0042'."""
    return re.sub(r"[^A-Z0-9]", "", (inv_no or "").upper())
