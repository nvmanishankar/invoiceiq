"""Pydantic models for the extraction (build guide section 9, stage 2).

These double as the Gemini response schema, so they stay within what the
structured-output schema supports: no free-form dicts, enums as Literals.
"""

from typing import Literal

from pydantic import BaseModel, Field

Level = Literal["high", "medium", "low"]
DocType = Literal["invoice", "quotation", "credit_note", "purchase_order", "delivery_note", "statement", "other"]


class ExtractedLine(BaseModel):
    description: str
    hsn: str | None = None
    qty: float | None = None
    unit: str | None = None
    unit_price: float | None = None  # excl. tax
    tax_rate: float | None = None
    amount: float | None = None  # line amount excl. tax


class FieldConfidence(BaseModel):
    invoice_number: Level | None = None
    invoice_date: Level | None = None
    total: Level | None = None
    vendor_gstin: Level | None = None
    bank_account: Level | None = None
    po_reference: Level | None = None


class ExtractedInvoice(BaseModel):
    page_range: list[int] = Field(default_factory=list)
    vendor_name: str | None = None
    vendor_gstin: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None  # ISO yyyy-mm-dd
    po_reference: str | None = None  # raw text as printed
    currency: str | None = None
    lines: list[ExtractedLine] = Field(default_factory=list)
    subtotal: float | None = None
    cgst: float | None = None
    sgst: float | None = None
    igst: float | None = None
    total: float | None = None
    tax_inclusive: bool = False
    bank_account: str | None = None
    ifsc: str | None = None
    payment_terms_days: int | None = None
    confidence: FieldConfidence = Field(default_factory=FieldConfidence)


class Extraction(BaseModel):
    doc_type: DocType
    invoices: list[ExtractedInvoice]
    boundaries_clear: bool = True


class PairScore(BaseModel):
    pair: int  # index into the numbered list sent in the prompt
    score: float  # 0-1: how likely both descriptions mean the same item


class SimilarityScores(BaseModel):
    scores: list[PairScore]
