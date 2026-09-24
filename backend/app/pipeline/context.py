"""Objects passed through the pipeline (build guide section 8)."""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from app.models import CompanySettings, PoLine, PurchaseOrder, Vendor
from app.utils.money import rupees_to_paise

SYSTEM_ERROR = "sys"


def code_label(code: str) -> str:
    """How a finding code is shown to people: 'sys' reads as 'System error'."""
    return "System error" if code == SYSTEM_ERROR else code


@dataclass
class Finding:
    code: str  # "3.2", "6.5" ... matches the design doc case ids
    severity: str  # "pass" | "hold" | "reject" | "info"
    message: str  # plain language for a finance reader
    audience: list[str]  # ["Vendor"], ["AP"], ["Finance","AP"], [] ...
    evidence: dict = field(default_factory=dict)
    fraud: bool = False  # a fraud finding blocks every vendor email for the run

    @property
    def label(self) -> str:
        return code_label(self.code)


@dataclass
class InvLine:
    line_no: int
    description: str
    qty: float | None
    unit_price_paise: int | None
    amount_paise: int | None
    tax_rate: float | None

    @property
    def taxable_paise(self) -> int | None:
        """Printed line amount, else qty x unit price, else None (never guessed)."""
        if self.amount_paise is not None:
            return self.amount_paise
        if self.qty is not None and self.unit_price_paise is not None:
            return round(self.qty * self.unit_price_paise)
        return None


@dataclass
class InvoiceFields:
    """Stage 2 output as typed values: money in paise, dates as date."""

    vendor_name: str | None
    vendor_gstin: str | None
    invoice_no: str | None
    invoice_date: date | None
    invoice_date_raw: str | None
    po_reference: str | None
    currency: str | None
    lines: list[InvLine]
    subtotal_paise: int | None
    cgst_paise: int | None
    sgst_paise: int | None
    igst_paise: int | None
    total_paise: int | None
    bank_account: str | None
    ifsc: str | None
    payment_terms_days: int | None

    @property
    def tax_paise(self) -> int:
        return sum(v or 0 for v in (self.cgst_paise, self.sgst_paise, self.igst_paise))


def _paise(v) -> int | None:
    return None if v is None else rupees_to_paise(v)


def _date(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def invoice_fields(ex: dict) -> InvoiceFields:
    return InvoiceFields(
        vendor_name=ex.get("vendor_name"),
        vendor_gstin=ex.get("vendor_gstin"),
        invoice_no=ex.get("invoice_number"),
        invoice_date=_date(ex.get("invoice_date")),
        invoice_date_raw=ex.get("invoice_date"),
        po_reference=ex.get("po_reference"),
        currency=ex.get("currency"),
        lines=[
            InvLine(i, ln.get("description") or "", ln.get("qty"), _paise(ln.get("unit_price")),
                    _paise(ln.get("amount")), ln.get("tax_rate"))
            for i, ln in enumerate(ex.get("lines") or [], start=1)
        ],
        subtotal_paise=_paise(ex.get("subtotal")),
        cgst_paise=_paise(ex.get("cgst")),
        sgst_paise=_paise(ex.get("sgst")),
        igst_paise=_paise(ex.get("igst")),
        total_paise=_paise(ex.get("total")),
        bank_account=ex.get("bank_account"),
        ifsc=ex.get("ifsc"),
        payment_terms_days=ex.get("payment_terms_days"),
    )


@dataclass
class LinePair:
    """An invoice line and the PO line it was matched to in stage 5."""

    inv: InvLine
    po_line: PoLine
    similarity: float


@dataclass
class RunContext:
    run_id: str
    file_bytes: bytes
    file_hash: str
    company: CompanySettings
    db: Session
    file_name: str | None = None
    today: date = field(default_factory=date.today)
    page_count: int = 0
    text: str = ""
    is_scan: bool = False
    llm_calls: int = 0
    doc_type: str | None = None
    extraction: dict | None = None  # stage 2 output (one ExtractedInvoice as a dict)
    bundled: bool = False  # stage 3: one line, no quantity (3.7)
    vendor: Vendor | None = None
    po: PurchaseOrder | None = None
    match_type: str = "None"
    match_confidence: str | None = None
    line_pairs: list[LinePair] = field(default_factory=list)
    unpaired_lines: list[InvLine] = field(default_factory=list)
    due_date: date | None = None
    decision: str | None = None
    findings: list[Finding] = field(default_factory=list)
    halt: bool = False  # only for "can't continue" (unreadable, not an invoice)
    _fields: InvoiceFields | None = field(default=None, repr=False)

    @property
    def inv(self) -> InvoiceFields:
        if self._fields is None:
            self._fields = invoice_fields(self.extraction or {})
        return self._fields

    def add(self, code: str, severity: str, message: str, audience: list[str],
            evidence: dict | None = None, fraud: bool = False) -> None:
        self.findings.append(Finding(code, severity, message, audience, evidence or {}, fraud))

    def codes(self) -> list[str]:
        return [f.code for f in self.findings]


def summarise(findings: list[Finding]) -> str:
    """One timeline line from several finding messages."""
    return " ".join(f.message for f in findings)


@dataclass
class StageResult:
    status: str  # "pass" | "warn" | "fail" | "info"
    message: str  # one line for the timeline
    details: dict = field(default_factory=dict)  # evidence shown when the stage is expanded
