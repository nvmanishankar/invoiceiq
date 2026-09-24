"""Purchase orders and tax rates (build guide section 12). Only Procurement may create or change a PO."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.roles import require_procurement
from app.services import purchasing
from app.services import runs as run_service

router = APIRouter(prefix="/api", tags=["purchase orders"])


@router.get("/pos")
def list_pos(db: Session = Depends(get_db)):
    """Every PO with totals, invoiced (approved only), remaining, and the invoices billed against it."""
    return purchasing.list_pos(db)


@router.get("/pos/next-id")
def next_po_id(db: Session = Depends(get_db)):
    """The number the next new PO will get. It's only reserved on save."""
    return {"po_id": purchasing.next_po_id(db, run_service.today().year), "today": run_service.today().isoformat()}


@router.post("/pos", status_code=201)
def create_po(body: purchasing.PoIn, x_role: str | None = Header(None), db: Session = Depends(get_db)):
    role = require_procurement(x_role, "raise purchase orders")
    po, warnings = purchasing.create_po(db, body, role, run_service.today())
    return {**purchasing.get_po(db, po.po_id), "warnings": warnings}


@router.get("/pos/{po_id}")
def get_po(po_id: str, db: Session = Depends(get_db)):
    out = purchasing.get_po(db, po_id)
    if out is None:
        raise HTTPException(404, f"PO {po_id} not found.")
    return out


class PoStatusBody(BaseModel):
    status: Literal["Open", "Closed"]


@router.patch("/pos/{po_id}")
def set_po_status(po_id: str, body: PoStatusBody, x_role: str | None = Header(None), db: Session = Depends(get_db)):
    """Close a PO (no more invoices can be paid against it) or reopen it."""
    require_procurement(x_role, "close or reopen purchase orders")
    purchasing.set_po_status(db, po_id, body.status)
    return purchasing.get_po(db, po_id)


@router.get("/tax-rates")
def tax_rates(country: str = Query("IN", min_length=2, max_length=2),
              on: date | None = Query(None, description="YYYY-MM-DD; defaults to today"),
              db: Session = Depends(get_db)):
    """GST slabs in force on a date: the only rates a PO line may use."""
    return [purchasing.rate_dict(r) for r in purchasing.valid_rates(db, country.upper(), on or run_service.today())]
