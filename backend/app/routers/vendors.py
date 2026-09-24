"""Vendor master (build guide section 12). Only Procurement may add, block or unblock a vendor."""

from typing import Literal

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.roles import require_procurement
from app.services import vendors as vendor_service

router = APIRouter(prefix="/api/vendors", tags=["vendors"])


@router.get("")
def list_vendors(db: Session = Depends(get_db)):
    return vendor_service.list_vendors(db)


@router.post("", status_code=201)
def create_vendor(body: vendor_service.VendorIn, x_role: str | None = Header(None), db: Session = Depends(get_db)):
    """Checks GSTIN format and checksum, IFSC, email; refuses a duplicate GSTIN or bank account."""
    role = require_procurement(x_role, "add vendors")
    return vendor_service.vendor_dict(vendor_service.create_vendor(db, body, role))


class VendorStatusBody(BaseModel):
    status: Literal["Active", "Blocked"]


@router.patch("/{vendor_id}")
def set_vendor_status(vendor_id: str, body: VendorStatusBody, x_role: str | None = Header(None),
                      db: Session = Depends(get_db)):
    """Block a vendor (their invoices are rejected, no new POs) or unblock them."""
    require_procurement(x_role, "block or unblock vendors")
    return vendor_service.vendor_dict(vendor_service.set_vendor_status(db, vendor_id, body.status))
