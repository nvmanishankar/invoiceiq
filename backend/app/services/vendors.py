"""Vendor master: list, Add vendor with checks, block/unblock (design doc, "Vendors and onboarding").

Two fraud checks run on save: a GSTIN that already belongs to another vendor, and a bank account
already on file for another vendor (two vendors paid into one account).
"""

import re

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CompanySettings, PurchaseOrder, Vendor, clip
from app.services.errors import Invalid
from app.utils.gstin import GSTIN_RE, STATE_NAMES, gstin_checksum, normalise_gstin, state_code, state_label
from app.utils.normalise import digits
from app.utils.timefmt import iso

IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
BANK_DIGITS = (9, 18)  # Indian account numbers
STATUSES = ("Active", "Blocked")


class VendorIn(BaseModel):
    name: str | None = None
    short_name: str | None = None
    gstin: str | None = None
    address: str | None = None
    phone: str | None = None
    bank_account: str | None = None
    ifsc: str | None = None
    bank_name: str | None = None
    contact_email: str | None = None
    msme: bool | None = None


def _text(v: str | None) -> str:
    return (v or "").strip()


def vendor_dict(v: Vendor, open_pos: int = 0) -> dict:
    code = state_code(v.tax_id or "") if v.tax_id else None
    last4 = digits(v.bank_account)[-4:]
    return {
        "vendor_id": v.vendor_id,
        "name": v.name,
        "short_name": v.short_name,
        "gstin": v.tax_id,
        "state_code": code,
        "state": state_label(code) if code else None,
        "country": v.country,
        "currency": v.currency,
        "msme": v.msme,
        "status": v.status,
        "bank_last4": last4 or None,
        "bank_masked": f"…{last4}" if last4 else None,
        "ifsc": v.ifsc_or_swift,
        "bank_name": v.bank_name,
        "contact_email": v.contact_email,
        "phone": v.phone,
        "open_pos": open_pos,
        "created_by": v.created_by,
        "created_at": iso(v.created_at),
    }


def list_vendors(db: Session) -> list[dict]:
    open_pos = dict(db.execute(select(PurchaseOrder.vendor_id, func.count()).where(PurchaseOrder.status == "Open")
                               .group_by(PurchaseOrder.vendor_id)).all())
    return [vendor_dict(v, open_pos.get(v.vendor_id, 0)) for v in db.scalars(select(Vendor).order_by(Vendor.vendor_id))]


def gstin_problem(g: str) -> str | None:
    """Why a GSTIN is invalid, in words a finance person can act on; None if it's fine."""
    if not g:
        return "Enter the vendor's GSTIN."
    if len(g) != 15:
        return f"A GSTIN has 15 characters; this one has {len(g)}."
    if not GSTIN_RE.match(g):
        return ("That isn't a GSTIN: it should be a 2-digit state code, the 10-character PAN, an entity number, "
                "'Z' and a check character (e.g. 36AABCA1234F1ZA).")
    if g[:2] not in STATE_NAMES:
        return f"The GSTIN starts with {g[:2]}, which isn't an Indian state code."
    if gstin_checksum(g[:14]) != g[14]:
        return "The check character doesn't match, so there's a typo somewhere in this GSTIN."
    return None


def next_vendor_id(db: Session) -> str:
    nums = [int(m.group(1)) for vid in db.scalars(select(Vendor.vendor_id)) if (m := re.fullmatch(r"V-(\d+)", vid))]
    return f"V-{max(nums + [0]) + 1:02d}"


def create_vendor(db: Session, body: VendorIn, role: str) -> Vendor:
    company = db.scalar(select(CompanySettings).limit(1))
    errors: dict[str, str] = {}
    name = _text(body.name)
    gstin = normalise_gstin(body.gstin)
    account = digits(body.bank_account)
    ifsc = _text(body.ifsc).upper()
    email = _text(body.contact_email)

    if not name:
        errors["name"] = "Enter the vendor's legal name."
    if problem := gstin_problem(gstin):
        errors["gstin"] = problem
    if not account:
        errors["bank_account"] = "Enter the bank account the vendor is paid into."
    elif _text(body.bank_account).replace(" ", "") != account or not BANK_DIGITS[0] <= len(account) <= BANK_DIGITS[1]:
        errors["bank_account"] = f"A bank account number is {BANK_DIGITS[0]} to {BANK_DIGITS[1]} digits, nothing else."
    if not ifsc:
        errors["ifsc"] = "Enter the branch IFSC."
    elif not IFSC_RE.match(ifsc):
        errors["ifsc"] = "An IFSC is 11 characters: 4 letters for the bank, a zero, then 6 letters or digits (e.g. HDFC0001234)."
    if not email:
        errors["contact_email"] = "Enter a contact email: it's where invoice problems are sent."
    elif not EMAIL_RE.match(email):
        errors["contact_email"] = "That doesn't look like an email address."
    if body.msme is None:
        errors["msme"] = "Say whether the vendor is an MSME: it caps their payment terms at 45 days."
    if errors:
        raise Invalid(errors)

    # Fraud checks, across every vendor including blocked ones.
    dupes: dict[str, str] = {}
    same_gstin = db.scalar(select(Vendor).where(Vendor.tax_id == gstin))
    if same_gstin is not None:
        dupes["gstin"] = f"This GSTIN already belongs to {same_gstin.name} ({same_gstin.vendor_id})."
    same_bank = next((v for v in db.scalars(select(Vendor)) if digits(v.bank_account) == account), None)
    if same_bank is not None:
        dupes["bank_account"] = (f"This bank account is already on file for {same_bank.name} ({same_bank.vendor_id}). "
                                 "Two vendors paid into one account is a fraud signal, so it can't be added.")
    if dupes:
        raise Invalid(dupes, status=409)

    vendor = Vendor(
        vendor_id=next_vendor_id(db),
        name=clip(Vendor, "name", name),
        short_name=clip(Vendor, "short_name", _text(body.short_name)) or None,
        address=_text(body.address) or None,
        country="IN",
        currency=company.currency if company else "INR",
        tax_id=gstin,
        bank_account=account,
        ifsc_or_swift=ifsc,
        bank_name=clip(Vendor, "bank_name", _text(body.bank_name)) or None,
        phone=clip(Vendor, "phone", _text(body.phone)) or None,
        contact_email=clip(Vendor, "contact_email", email),
        msme=body.msme,
        status="Active",
        created_by=role,
    )
    db.add(vendor)
    db.commit()
    return vendor


def set_vendor_status(db: Session, vendor_id: str, status: str) -> Vendor:
    vendor = db.get(Vendor, vendor_id)
    if vendor is None:
        raise Invalid({"vendor_id": f"Vendor {vendor_id} not found."}, status=404)
    if status not in STATUSES:
        raise Invalid({"status": "A vendor can be Active or Blocked."})
    vendor.status = status
    db.commit()
    return vendor
