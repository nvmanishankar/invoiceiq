"""The role selector (design doc, "Users"). Sent as the X-Role header; not real logins.

Segregation of duties: whoever raises a PO or onboards a vendor must not be the one approving invoices
against it, so only Procurement may change the purchasing master data.
"""

from fastapi import HTTPException

PROCUREMENT = "Procurement"
AP_CLERK = "AP clerk"
FINANCE = "Finance"
ROLES = (PROCUREMENT, AP_CLERK, FINANCE)
DEFAULT_ROLE = AP_CLERK


def role_of(header: str | None) -> str:
    """The caller's role; no header means the default role, never a more powerful one."""
    role = (header or "").strip()
    return role if role in ROLES else DEFAULT_ROLE


def require_procurement(header: str | None, action: str) -> str:
    """403 unless the caller is Procurement. `action` completes 'Only Procurement can …'."""
    role = role_of(header)
    if role != PROCUREMENT:
        raise HTTPException(403, f"Only Procurement can {action}. You're signed in as {role}: the people who "
                                 "approve invoices must not also control POs and vendors (segregation of duties).")
    return role
