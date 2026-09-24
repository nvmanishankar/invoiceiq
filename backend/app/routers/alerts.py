"""Outbox: every alert, and 'Send' for drafted ones (build guide sections 10 and 12)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import alerts
from app.db import get_db
from app.models import Alert, Invoice

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
def list_alerts(
    status: str | None = Query(None, description="Drafted / Sent / Failed"),
    run_id: str | None = None,
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(Alert, Invoice).join(Invoice, Invoice.run_id == Alert.run_id)
    if status:
        stmt = stmt.where(Alert.status == status)
    if run_id:
        stmt = stmt.where(Alert.run_id == run_id)
    rows = db.execute(stmt.order_by(Alert.alert_id.desc()).limit(limit)).all()
    return [alerts.alert_dict(a, inv) for a, inv in rows]


@router.post("/{alert_id}/send")
def send_alert(alert_id: int, db: Session = Depends(get_db)):
    """Send a Drafted alert now. A Failed one can be retried the same way."""
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, f"Alert {alert_id} not found.")
    if alert.status == "Sent":
        raise HTTPException(409, "This alert was already sent.")
    try:
        alerts.send_drafted(db, alert)
    except alerts.VendorEmailBlocked as e:
        raise HTTPException(409, str(e))
    return alerts.alert_dict(alert, db.get(Invoice, alert.run_id))
