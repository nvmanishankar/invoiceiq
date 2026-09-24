"""Money helpers. Amounts are integer paise (Rs 1 = 100)."""

from decimal import ROUND_HALF_UP, Decimal


def rupees_to_paise(rupees: float | int | str | Decimal) -> int:
    return int((Decimal(str(rupees)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def allowed_diff(expected_paise: int, tolerance_pct: float, tolerance_abs_paise: int) -> int:
    """min(pct of expected, absolute cap). Rs 1,00,000 at 2% / Rs 5,000 cap → Rs 2,000."""
    pct_part = int((Decimal(abs(expected_paise)) * Decimal(str(tolerance_pct))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return min(pct_part, tolerance_abs_paise)


def within_tolerance(actual_paise: int, expected_paise: int, tolerance_pct: float, tolerance_abs_paise: int) -> bool:
    return abs(actual_paise - expected_paise) <= allowed_diff(expected_paise, tolerance_pct, tolerance_abs_paise)


def _group_indian(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


def format_inr(paise: int | None, symbol: str = "₹") -> str:
    """11800000 → '₹1,18,000'; paise shown only when non-zero: 11800050 → '₹1,18,000.50'."""
    if paise is None:
        return "—"
    sign = "-" if paise < 0 else ""
    rupees, rem = divmod(abs(int(paise)), 100)
    out = f"{sign}{symbol}{_group_indian(rupees)}"
    return out + (f".{rem:02d}" if rem else "")
