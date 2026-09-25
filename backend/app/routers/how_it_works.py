"""The "How it works" page: case catalogue, PO-matching walkthrough, GST rate history, vendor loop, facts. Read-only."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import how_it_works

router = APIRouter(prefix="/api/how-it-works", tags=["how-it-works"])


@router.get("/cases")
def cases():
    """All 62 design-doc cases, as the code handles them today."""
    return how_it_works.cases()


@router.get("/po-walkthrough")
def po_walkthrough():
    """Sample 03's PO matching, run through the real pipeline on a scratch copy of the seed data."""
    try:
        return how_it_works.po_walkthrough()
    except LookupError as e:
        raise HTTPException(503, str(e))


@router.get("/tax-rates")
def tax_rates(db: Session = Depends(get_db)):
    """Every Indian GST rate with its start and end dates, ended ones included."""
    return how_it_works.tax_rates(db)


@router.get("/vendor-loop")
def vendor_loop():
    """Sample 04 held for over-billing, run on a scratch copy: the autofilled vendor email and the vendor's page."""
    try:
        return how_it_works.vendor_loop()
    except LookupError as e:
        raise HTTPException(503, str(e))


@router.get("/facts")
def facts():
    """Who may do what, limits and test counts, from the code that enforces them."""
    return how_it_works.facts()
