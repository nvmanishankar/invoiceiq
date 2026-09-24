"""The role selector (design doc, "Users"). Sent as the X-Role header; not real logins.

Segregation of duties: whoever raises a PO or onboards a vendor must not be the one approving invoices
against it, so only Procurement may change the purchasing master data. Tolerance is a financial control, so
only Finance may change it.
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


def require_finance(header: str | None, action: str) -> str:
    """403 unless the caller is Finance. `action` completes 'Only Finance can …'."""
    role = role_of(header)
    if role != FINANCE:
        raise HTTPException(403, f"Only Finance can {action}. You're signed in as {role}: how far an invoice may "
                                 "differ from its PO is a financial control, so Finance owns it.")
    return role
