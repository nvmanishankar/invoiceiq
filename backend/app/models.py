"""SQLAlchemy tables (build guide section 5). Money is integer paise."""

from datetime import date, datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CompanySettings(Base):
    __tablename__ = "company_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str] = mapped_column(String(2))
    gstin: Mapped[str | None] = mapped_column(String(15))
    state_code: Mapped[str | None] = mapped_column(String(2))
    currency: Mapped[str] = mapped_column(String(3))
    tolerance_pct: Mapped[float] = mapped_column(Float, default=0.02)
    tolerance_abs_paise: Mapped[int] = mapped_column(BigInteger, default=500000)
    ap_email: Mapped[str] = mapped_column(String(200))
    procurement_email: Mapped[str] = mapped_column(String(200))
    finance_email: Mapped[str] = mapped_column(String(200))
    vendor_auto_send: Mapped[bool] = mapped_column(Boolean, default=True)


class Vendor(Base):
    __tablename__ = "vendors"

    vendor_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    short_name: Mapped[str | None] = mapped_column(String(100))
    address: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str] = mapped_column(String(2))
    currency: Mapped[str] = mapped_column(String(3))
    tax_id: Mapped[str | None] = mapped_column(String(30), index=True)
    bank_account: Mapped[str | None] = mapped_column(String(40))
    ifsc_or_swift: Mapped[str | None] = mapped_column(String(20))
    bank_name: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(40))
    contact_email: Mapped[str | None] = mapped_column(String(200))
    msme: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="Active")  # Active / Blocked
    created_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(back_populates="vendor")


class TaxRate(Base):
    __tablename__ = "tax_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    country: Mapped[str] = mapped_column(String(2))
    tax_name: Mapped[str] = mapped_column(String(20))
    rate: Mapped[float] = mapped_column(Float)
    label: Mapped[str | None] = mapped_column(String(100))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    po_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.vendor_id"))
    po_date: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3))
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    department: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="Open")  # Open / Closed / Cancelled
    created_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    vendor: Mapped[Vendor] = relationship(back_populates="purchase_orders")
    lines: Mapped[list["PoLine"]] = relationship(
        back_populates="po", order_by="PoLine.line_no", cascade="all, delete-orphan"
    )


class PoLine(Base):
    __tablename__ = "po_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    po_id: Mapped[str] = mapped_column(ForeignKey("purchase_orders.po_id"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    hsn_code: Mapped[str | None] = mapped_column(String(20))
    qty: Mapped[float] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(20))
    unit_price_paise: Mapped[int] = mapped_column(BigInteger)
    tax_rate: Mapped[float] = mapped_column(Float)

    po: Mapped[PurchaseOrder] = relationship(back_populates="lines")


class GoodsReceipt(Base):
    __tablename__ = "goods_receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    po_id: Mapped[str] = mapped_column(ForeignKey("purchase_orders.po_id"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    qty_received: Mapped[float] = mapped_column(Float)
    received_date: Mapped[date | None] = mapped_column(Date)


class Invoice(Base):
    """One row per run: the ledger."""

    __tablename__ = "invoices"

    run_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    parent_upload_id: Mapped[str | None] = mapped_column(String(30))
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    doc_type: Mapped[str | None] = mapped_column(String(30))
    # running / needs_review / waiting_on_vendor / approved / held / rejected
    status: Mapped[str] = mapped_column(String(30), default="running")
    invoice_no: Mapped[str | None] = mapped_column(String(100))
    invoice_no_norm: Mapped[str | None] = mapped_column(String(100), index=True)
    invoice_date: Mapped[date | None] = mapped_column(Date)
    vendor_tax_id: Mapped[str | None] = mapped_column(String(30))
    vendor_id: Mapped[str | None] = mapped_column(ForeignKey("vendors.vendor_id"), index=True)
    po_id: Mapped[str | None] = mapped_column(ForeignKey("purchase_orders.po_id"), index=True)
    po_match_type: Mapped[str] = mapped_column(String(30), default="None")  # Explicit / Inferred / None
    match_confidence: Mapped[str | None] = mapped_column(String(20))
    subtotal_paise: Mapped[int | None] = mapped_column(BigInteger)
    cgst_paise: Mapped[int | None] = mapped_column(BigInteger)
    sgst_paise: Mapped[int | None] = mapped_column(BigInteger)
    igst_paise: Mapped[int | None] = mapped_column(BigInteger)
    total_paise: Mapped[int | None] = mapped_column(BigInteger)
    bank_account: Mapped[str | None] = mapped_column(String(40))
    decision: Mapped[str | None] = mapped_column(String(20))  # Approve / Hold / Reject
    decision_reasons: Mapped[list | None] = mapped_column(JSON)
    due_date: Mapped[date | None] = mapped_column(Date)
    extraction: Mapped[dict | None] = mapped_column(JSON)
    processed_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_seed: Mapped[bool] = mapped_column(Boolean, default=False)

    vendor: Mapped[Vendor | None] = relationship()
    po: Mapped[PurchaseOrder | None] = relationship()
    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice", order_by="InvoiceLine.line_no", cascade="all, delete-orphan"
    )


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("invoices.run_id"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    qty: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(20))
    unit_price_paise: Mapped[int | None] = mapped_column(BigInteger)
    tax_rate: Mapped[float | None] = mapped_column(Float)
    matched_po_line: Mapped[int | None] = mapped_column(Integer)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class RunStage(Base):
    __tablename__ = "run_stages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("invoices.run_id"), index=True)
    stage_order: Mapped[int] = mapped_column(Integer)
    stage_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(10))  # pass / warn / fail / info
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSON)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("invoices.run_id"), index=True)
    reviewer: Mapped[str | None] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str | None] = mapped_column(Text)
    field_changes: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"

    alert_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("invoices.run_id"), index=True)
    audience: Mapped[str] = mapped_column(String(20))  # Vendor / AP / Procurement / Finance
    intended_for: Mapped[str | None] = mapped_column(String(200))
    to_email: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="Drafted")  # Drafted / Sent / Failed
    response_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    token_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
