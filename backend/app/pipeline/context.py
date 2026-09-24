"""Objects passed through the pipeline (build guide section 8)."""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import CompanySettings, PurchaseOrder, Vendor


@dataclass
class Finding:
    code: str  # "3.2", "6.5" ... matches the design doc case ids
    severity: str  # "pass" | "hold" | "reject" | "info"
    message: str  # plain language for a finance reader
    audience: list[str]  # ["Vendor"], ["AP"], ["Finance","AP"], [] ...
    evidence: dict = field(default_factory=dict)


@dataclass
class RunContext:
    run_id: str
    file_bytes: bytes
    file_hash: str
    company: CompanySettings
    db: Session
    file_name: str | None = None
    page_count: int = 0
    text: str = ""
    is_scan: bool = False
    llm_calls: int = 0
    doc_type: str | None = None
    extraction: dict | None = None  # stage 2 output (one ExtractedInvoice as a dict)
    vendor: Vendor | None = None
    po: PurchaseOrder | None = None
    match_type: str = "None"
    match_confidence: str | None = None
    line_pairs: list = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    halt: bool = False  # only for "can't continue" (unreadable, not an invoice)

    def add(self, code: str, severity: str, message: str, audience: list[str], evidence: dict | None = None) -> None:
        self.findings.append(Finding(code, severity, message, audience, evidence or {}))


@dataclass
class StageResult:
    status: str  # "pass" | "warn" | "fail" | "info"
    message: str  # one line for the timeline
    details: dict = field(default_factory=dict)  # evidence shown when the stage is expanded
