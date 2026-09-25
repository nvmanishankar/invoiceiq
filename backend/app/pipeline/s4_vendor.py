"""Stage 4: verify the vendor by GSTIN, name only as a fallback (cases 4.1-4.7)."""

import re

from rapidfuzz import fuzz
from sqlalchemy import select

from app.models import Vendor
from app.pipeline.context import RunContext, StageResult, summarise
from app.utils.gstin import normalise_gstin, valid_gstin
from app.utils.normalise import company_name_key, digits

NAME_MATCH_MIN = 90  # rapidfuzz score, 0-100


def name_score(a: str | None, b: str | None) -> float:
    ka, kb = company_name_key(a), company_name_key(b)
    if not ka or not kb:
        return 0.0
    return fuzz.token_sort_ratio(ka, kb)


def best_name_match(db, name: str | None) -> Vendor | None:
    scored = [(max(name_score(name, v.name), name_score(name, v.short_name)), v) for v in db.scalars(select(Vendor))]
    scored = [(s, v) for s, v in scored if s >= NAME_MATCH_MIN]
    return max(scored, key=lambda sv: sv[0])[1] if scored else None


def _last4(s: str | None) -> str:
    return digits(s)[-4:]


def _ifsc(s: str | None) -> str:
    return re.sub(r"\s", "", s or "").upper()


def check_bank(ctx: RunContext, vendor: Vendor) -> None:
    """Case 4.7: the payee on the invoice must be the account on file: same number and, when both give one, the same
    IFSC (the same number at another branch is another account). No bank details means we pay the account on file."""
    inv = ctx.inv
    if not inv.bank_account:
        ctx.add("4.7", "info", "No bank details on the invoice; payment goes to the account on file.", [],
                {"file_account_last4": _last4(vendor.bank_account)})
        return
    evidence = {"invoice_account_last4": _last4(inv.bank_account), "file_account_last4": _last4(vendor.bank_account),
                "invoice_ifsc": inv.ifsc, "file_ifsc": vendor.ifsc_or_swift, "phone_on_file": vendor.phone}
    if digits(inv.bank_account) != digits(vendor.bank_account):
        ctx.add("4.7", "hold",
                f"The bank account on the invoice (…{_last4(inv.bank_account)}) differs from the one on file "
                f"(…{_last4(vendor.bank_account)}). Fraud risk: verify by phone using the number on file.",
                ["Finance", "AP"], evidence, fraud=True)
    elif _ifsc(inv.ifsc) and _ifsc(vendor.ifsc_or_swift) and _ifsc(inv.ifsc) != _ifsc(vendor.ifsc_or_swift):
        ctx.add("4.7", "hold",
                f"The account number matches the one on file (…{_last4(vendor.bank_account)}), but the IFSC on the "
                f"invoice ({_ifsc(inv.ifsc)}) differs from the one on file ({_ifsc(vendor.ifsc_or_swift)}), so the "
                "money would go to a different bank. Fraud risk: verify by phone using the number on file.",
                ["Finance", "AP"], evidence, fraud=True)


def run(ctx: RunContext) -> StageResult:
    inv = ctx.inv
    g = normalise_gstin(inv.vendor_gstin) or None
    g_valid = bool(g) and valid_gstin(g)
    printed_name = inv.vendor_name or "The vendor"
    if g and not g_valid:
        ctx.add("4.3", "hold", f"The GSTIN on the invoice ({g}) isn't valid.", ["Vendor"], {"gstin": g})

    vendor = ctx.db.scalar(select(Vendor).where(Vendor.tax_id == g)) if g_valid else None
    how = "GSTIN"
    if vendor is not None:
        if vendor.status == "Blocked":
            pass  # reported as 4.5 below, not as an approved vendor
        elif name_score(inv.vendor_name, vendor.name) >= NAME_MATCH_MIN or \
                name_score(inv.vendor_name, vendor.short_name) >= NAME_MATCH_MIN or not inv.vendor_name:
            ctx.add("4.1", "pass", f"{vendor.name} is an approved vendor (GSTIN {vendor.tax_id}).", [])
        else:
            ctx.add("4.2", "pass", f"The name on the invoice ('{inv.vendor_name}') differs from the vendor master "
                                   f"('{vendor.name}'), but the GSTIN matches.", [])
    else:
        by_name = best_name_match(ctx.db, inv.vendor_name)
        if by_name and g_valid:
            ctx.add("4.6", "hold", f"The name matches {by_name.name}, but the GSTIN {g} doesn't match the one on file "
                                   f"({by_name.tax_id}). Possible impersonation.", ["Finance", "AP"],
                    {"gstin_on_invoice": g, "gstin_on_file": by_name.tax_id, "vendor_id": by_name.vendor_id}, fraud=True)
        elif by_name:
            vendor, how = by_name, "name"
            reason = "No GSTIN on the invoice" if not g else "The GSTIN on the invoice isn't valid"
            ctx.add("4.2", "info", f"{reason}; vendor identified by name as {by_name.name}.", [],
                    {"vendor_id": by_name.vendor_id})
        else:
            gst = f"GSTIN {g}" if g else "no GSTIN"
            ctx.add("4.4", "hold", f"{printed_name} ({gst}) isn't an approved vendor.", ["Procurement"],
                    {"name": inv.vendor_name, "gstin": g})

    if vendor is not None and vendor.status == "Blocked":
        ctx.add("4.5", "reject", f"{vendor.name} is blocked in the vendor master.", ["Procurement"],
                {"vendor_id": vendor.vendor_id})

    if vendor is not None:
        check_bank(ctx, vendor)

    ctx.vendor = vendor
    details = {"gstin": g, "gstin_valid": g_valid, "vendor_id": vendor.vendor_id if vendor else None, "matched_by": how}
    if vendor is None:
        return StageResult("warn", "Vendor not verified", details)
    problems = [f for f in ctx.findings if f.code.startswith("4.") and f.severity in ("hold", "reject")]
    if problems:
        return StageResult("fail" if any(f.severity == "reject" for f in problems) else "warn",
                           summarise(problems), details)
    return StageResult("pass", f"{vendor.name} verified by {how}", details)
