# InvoiceIQ — Build Guide (for Claude Code in VS Code)

Companion to `InvoiceIQ_Solution_Design_PS1.md`. The design doc says **what** we build and **why**. This guide says **how**: the free stack, every module's logic with worked examples, the seed data, the order to build in, and the exact prompts to give Claude Code.

Owner and every email address in the system: **nvmanishankar@gmail.com**

---

## 0. The rules for this build

1. **Everything is free.** No paid API, no paid hosting, no credit card if avoidable.
2. **Everything is live.** One public URL runs the real pipeline on real PDFs. No mocks.
3. **One email for everything.** Vendor contacts, AP team, Procurement, Finance, and the sender account all use `nvmanishankar@gmail.com`. Each email says who it was *meant* for, so the routing is still visible.
4. **Happy path first, then edge cases one at a time.** Commit after every working step.
5. **AI reads, rules decide.** The LLM extracts and compares text. Python rules make every decision.

---

## 1. The free stack

| Layer | Tool | Free tier notes | Why this one |
| --- | --- | --- | --- |
| Code editor + AI builder | VS Code + Claude Code | Your own subscription | Builds the project from this guide |
| Backend | Python 3.11, FastAPI, Uvicorn | Open source | Pipeline stays in Python; easy streaming |
| Database (local) | SQLite | Built into Python | Zero setup while building |
| Database (live) | **Neon** Postgres | Free project, no card | Survives restarts; free hosting disks get wiped |
| ORM | SQLAlchemy 2 + psycopg | Open source | Same code for SQLite and Postgres |
| LLM | **Google Gemini API** via AI Studio | Free tier, no card. Flash-Lite models have the largest free daily quota; check your live quota in AI Studio | Reads PDFs and images directly, supports structured JSON output |
| PDF reading | pdfplumber, pypdfium2 | Open source | Text layer + render scans to images |
| Fuzzy matching | rapidfuzz | Open source | Fallback text similarity when the LLM quota is used up |
| Email | **Resend** | Free: 100/day, 3,000/month. Without a custom domain it sends only to the email you signed up with | Perfect: every alert goes to your one Gmail |
| Frontend | React + Vite + TypeScript | Open source | Fast dev, simple build |
| UI kit | Tailwind CSS, shadcn/ui, lucide-react, Framer Motion, Recharts | Open source | Polished UI, animated timeline, charts |
| Data fetching | TanStack Query | Open source | Caching, refetch on focus |
| Hosting | **Render** free web service (Docker) | Sleeps after ~15 min idle, ~1 min wake-up | One URL serves API + React |
| Code hosting | GitHub | Free | Render deploys from it |
| Keep-awake (optional) | UptimeRobot | Free 5-minute pings | Avoids cold starts before the interview |
| Demo video | Loom free plan | 5-minute cap on free plan | Exactly the brief's limit |
| Sample PDFs | reportlab, Pillow | Open source | Generate realistic invoices and fake scans |

Sign up for Neon, Resend, Render, GitHub, Google AI Studio and UptimeRobot with **nvmanishankar@gmail.com**. For Resend this matters: its test sender only delivers to the account's own email.

### Why Gemini instead of Claude for the running app

The Claude API has no free tier. Gemini Flash-Lite does. The LLM sits behind a small adapter (`llm.py`), so switching to Claude later is one file. Say this in the interview: *"The pipeline is provider-agnostic; I used Gemini's free tier to keep the live demo at zero cost."*

**Quota discipline** (free tiers have daily request caps):
- At most **2 LLM calls per invoice**: one extraction call, and one description-matching call only when PO inference is needed.
- **Cache extraction by file hash.** Re-running the same sample costs zero calls. This also makes the demo fast and repeatable.
- **Emails use templates, not the LLM.**
- If the LLM fails or quota is exhausted, the run goes to **Hold: "Couldn't read this invoice automatically"** instead of crashing, and description matching falls back to rapidfuzz.

---

## 2. Architecture in one picture

```
Browser (React)
   │  POST /api/runs (PDF or sample)          ─┐
   │  GET  /api/runs/{id}/stream  (SSE)        │  one Render web service
   ▼                                           │  (Docker: FastAPI serves
FastAPI ── BackgroundTask ── Pipeline ─────────┤   the built React files)
   │                          │                │
   │                          ├── Gemini API (extract, compare)
   │                          ├── Rules (Python)
   │                          └── writes run_stages rows
   ├── Neon Postgres (all tables)
   └── Resend (alerts → nvmanishankar@gmail.com)
```

**How live streaming works (simple and robust):**
1. `POST /api/runs` saves the file, creates an `invoices` row with status `running`, starts the pipeline as a background task, and returns `run_id` immediately.
2. The pipeline writes one `run_stages` row as each stage finishes.
3. `GET /api/runs/{id}/stream` is a Server-Sent Events endpoint that polls `run_stages` every 400 ms and pushes any new rows. It ends when the run reaches a final status.
4. React opens an `EventSource` and animates each stage in.

Polling the database (instead of in-memory queues) means a page refresh, a second viewer, or a dropped connection still sees every stage. Each stage also waits a minimum of ~400 ms before writing, so humans can follow it on screen. Say that honestly if asked: it's a readability choice.

---

## 3. Repository layout

```
invoiceiq/
├── CLAUDE.md                      # instructions Claude Code reads every session
├── README.md                      # what it is, assumptions, how to run
├── Dockerfile                     # builds React, then runs FastAPI
├── .env.example
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                # FastAPI app, routers, static files
│   │   ├── config.py              # env settings
│   │   ├── db.py                  # engine, session, Base
│   │   ├── models.py              # SQLAlchemy tables
│   │   ├── schemas.py             # Pydantic models (extraction, API)
│   │   ├── seed.py                # seed data + reset
│   │   ├── llm.py                 # Gemini adapter (+ cache, fallback)
│   │   ├── prompts.py             # extraction + matching prompts
│   │   ├── alerts.py              # templates, routing, Resend send
│   │   ├── tax/
│   │   │   ├── __init__.py        # get_tax_model(country)
│   │   │   ├── india_gst.py
│   │   │   └── manual.py
│   │   ├── utils/
│   │   │   ├── gstin.py           # format, state code, checksum
│   │   │   ├── normalise.py       # invoice no, PO ref, names
│   │   │   └── money.py           # tolerance, rounding
│   │   ├── pipeline/
│   │   │   ├── context.py         # RunContext passed through stages
│   │   │   ├── runner.py          # runs stages, writes run_stages
│   │   │   ├── s1_read.py
│   │   │   ├── s2_extract.py
│   │   │   ├── s3_validate.py
│   │   │   ├── s4_vendor.py
│   │   │   ├── s5_po_match.py
│   │   │   ├── s6_amounts.py
│   │   │   ├── s7_duplicates.py
│   │   │   ├── s8_tax.py
│   │   │   ├── s9_dates.py
│   │   │   └── decide.py
│   │   └── routers/
│   │       ├── runs.py            # upload, stream, list, detail, review
│   │       ├── pos.py
│   │       ├── vendors.py
│   │       ├── alerts.py
│   │       ├── respond.py         # vendor response link
│   │       ├── stats.py
│   │       └── admin.py           # reset, test suite
│   ├── samples/                   # generated invoice PDFs + expected.json
│   ├── fixtures/extractions/      # cached extraction JSON per sample
│   ├── scripts/
│   │   ├── make_seed_and_samples.py  # seed JSON + sample PDFs (seed kit)
│   │   └── run_cli.py             # run pipeline from terminal
│   └── tests/
└── frontend/
    ├── package.json
    ├── index.html
    └── src/
        ├── main.tsx, App.tsx, api.ts, types.ts
        ├── components/            # StageTimeline, DecisionCard, CompareTable, ...
        └── pages/                 # Process, Review, Dashboard, POs, Vendors, Outbox, Tests, Settings, Respond
```

---

## 4. Environment variables

`.env.example`:

```bash
# Database: local SQLite by default; Neon URL in production
DATABASE_URL=sqlite:///./invoiceiq.db
# DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/DB?sslmode=require

# Gemini (Google AI Studio → Get API key)
GEMINI_API_KEY=
GEMINI_MODEL=            # set to the current Flash-Lite model ID shown in AI Studio
GEMINI_MODEL_FALLBACK=   # optional second model ID if the first hits its quota

# Email (Resend, account created with nvmanishankar@gmail.com)
RESEND_API_KEY=
EMAIL_FROM=InvoiceIQ <onboarding@resend.dev>
OWNER_EMAIL=nvmanishankar@gmail.com

# App
BASE_URL=http://localhost:8000          # live: https://<your-app>.onrender.com
MAX_RUNS_PER_DAY=60
VENDOR_AUTO_SEND=true                    # true for demo; false = click-to-send
MIN_STAGE_MS=400
```

Never commit `.env`. On Render, paste these into the service's Environment tab.

---

## 5. Data model (SQLAlchemy)

Tables exactly as in the design doc, plus one light table for three-way matching. Money is stored as **integer paise** (₹1 = 100) to avoid float errors; the API converts to rupees.

```python
# models.py (shape, not every column)
class CompanySettings(Base):   # single row
    id, name, country, gstin, state_code, currency,
    tolerance_pct (float, 0.02), tolerance_abs_paise (int, 500000),
    ap_email, procurement_email, finance_email, vendor_auto_send (bool)

class Vendor(Base):
    vendor_id (PK "V-01"), name, country, currency, tax_id, bank_account,
    ifsc_or_swift, contact_email, msme (bool), status ("Active"/"Blocked"),
    created_by, created_at

class TaxRate(Base):
    id, country, tax_name, rate (float), label, valid_from (date), valid_to (date|None)

class PurchaseOrder(Base):
    po_id (PK "PO-2026-104"), vendor_id (FK), po_date, currency,
    payment_terms_days, department, status ("Open"/"Closed"/"Cancelled"),
    created_by, created_at
    lines = relationship(PoLine)

class PoLine(Base):
    id, po_id (FK), line_no, description, hsn_code, qty (float), unit,
    unit_price_paise (int), tax_rate (float)

class GoodsReceipt(Base):              # optional three-way match
    id, po_id, line_no, qty_received, received_date

class Invoice(Base):                   # one row per run = the ledger
    run_id (PK "RUN-0042"), parent_upload_id, file_name, file_hash, doc_type,
    status ("running"/"needs_review"/"waiting_on_vendor"/"approved"/"held"/"rejected"),
    invoice_no, invoice_no_norm, invoice_date, vendor_tax_id, vendor_id, po_id,
    po_match_type ("Explicit"/"Inferred"/"None"), match_confidence,
    subtotal_paise, cgst_paise, sgst_paise, igst_paise, total_paise,
    bank_account, decision, decision_reasons (JSON), due_date,
    extraction (JSON), processed_by, created_at, finished_at, is_seed (bool)

class InvoiceLine(Base):
    id, run_id (FK), line_no, description, qty, unit, unit_price_paise,
    tax_rate, matched_po_line

class RunStage(Base):
    id, run_id (FK), stage_order, stage_name, status ("pass"/"warn"/"fail"/"info"),
    message, details (JSON), duration_ms, created_at

class Review(Base):
    id, run_id, reviewer, action, reason, field_changes (JSON), created_at

class Alert(Base):
    alert_id, run_id, audience ("Vendor"/"AP"/"Procurement"/"Finance"),
    intended_for (e.g. "Acme Supplies — accounts"), to_email, subject, body,
    status ("Drafted"/"Sent"/"Failed"), response_token, token_expires, sent_at
```

**Calculated on read, never stored:**

```python
def po_total_paise(po):     # sum over lines: qty * unit_price * (1 + rate/100)
def po_invoiced_paise(po_id, exclude_run=None):
    # SUM(total_paise) FROM invoices WHERE po_id=? AND decision='Approve' AND run_id != exclude_run
def po_remaining_paise(po): return po_total_paise(po) - po_invoiced_paise(po.po_id)
def invoiced_qty(po_id, line_no):   # SUM(invoice_lines.qty) over approved invoices
```

---

## 6. Seed data (designed so every edge case triggers)

Company: **Nimbus Retail Pvt Ltd**, Hyderabad, Telangana, state code **36**. All GST at 18% for simplicity. All emails = `nvmanishankar@gmail.com`.

GSTINs below show state code + PAN; the seed script **computes the final checksum character** with the function in section 9 so they all pass validation.

### Vendors

| ID | Name | State | GSTIN (first 14 chars) | Bank account | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| V-01 | Acme Supplies Private Limited | Telangana (36) | 36AABCA1234F1Z | 50100234564521 / HDFC0001234 | Active | Intra-state |
| V-02 | BrightTech Solutions Pvt Ltd | Karnataka (29) | 29AAFCB5678K1Z | 91201004455667 / UTIB0000123 | Active | Inter-state |
| V-03 | Zenith Logistics LLP | Delhi (07) | 07AAGCZ9012M1Z | 30112233445566 / SBIN0004567 | Active | Services |
| V-04 | Deccan Office Interiors | Telangana (36) | 36AAKFD3456Q1Z | 61234567890123 / ICIC0001122 | Active | MSME = yes |
| V-05 | Sahyadri Print House | Maharashtra (27) | 27AAHCS7788L1Z | 77889900112233 / KKBK0000456 | Active | Duplicate case |
| V-06 | Quickfix Traders | Tamil Nadu (33) | 33AAQFQ1122B1Z | 11223344556677 / IOBA0000789 | Blocked | Blocked case |

### Purchase orders (all prices excl. GST; 18% on every line)

| PO | Vendor | Date | Status | Lines | Total incl. GST |
| --- | --- | --- | --- | --- | --- |
| PO-2026-101 | V-01 | 02 Jun 2026 | Open | A4 copier paper 75gsm, 2,000 reams @ ₹200 | ₹4,72,000 |
| PO-2026-104 | V-01 | 20 Aug 2026 | Open | Ergonomic office chair, mesh back, 20 @ ₹5,000; Chair floor mat, 20 @ ₹1,300 | ₹1,48,680 |
| PO-2026-117 | V-01 | 10 Sep 2026 | Open | Standard office chair, 25 @ ₹4,000 | ₹1,18,000 |
| PO-2026-105 | V-02 | 28 Aug 2026 | Open | Dell Latitude 5440 laptop i5 16GB, 10 @ ₹65,000; Laptop backpack 15.6", 10 @ ₹1,200 | ₹7,81,160 |
| PO-2026-116 | V-02 | 15 Sep 2026 | Open | 27" IPS monitor, 15 @ ₹14,000 | ₹2,47,800 |
| PO-2026-108 | V-03 | 05 Sep 2026 | Open | Freight Hyderabad–Delhi, 12 trips @ ₹25,000 | ₹3,54,000 |
| PO-2026-109 | V-04 | 01 Sep 2026 | Open | Workstation desk 1400mm, 10 @ ₹18,000; Pedestal drawer unit, 10 @ ₹4,500 | ₹2,65,500 |
| PO-2026-110 | V-04 | 05 Sep 2026 | Open | Conference table 8-seater, 2 @ ₹35,000 | ₹82,600 |
| PO-2026-112 | V-05 | 10 Jul 2026 | **Closed** | Tri-fold brochures, 10,000 @ ₹8 | ₹94,400 |
| PO-2026-114 | V-05 | 25 Aug 2026 | Open | Printed brochures A4, 5,000 @ ₹12 | ₹70,800 |

Payment terms: 30 days for all; PO-2026-109 set to 60 days (to show the MSME cap of 45).

### Ledger: already-approved invoices (seeded, `is_seed = true`)

| Invoice no | Vendor | PO | Date | Qty | Total |
| --- | --- | --- | --- | --- | --- |
| ACME/2026/0311 | V-01 | PO-2026-101 | 10 Jul 2026 | 800 reams | ₹1,88,800 |
| ACME/2026/0388 | V-01 | PO-2026-101 | 12 Aug 2026 | 700 reams | ₹1,65,200 |
| SPH/INV-0042 | V-05 | PO-2026-114 | 05 Sep 2026 | 5,000 brochures | ₹70,800 |

So PO-2026-101 has **₹1,18,000 (500 reams) remaining**, and PO-2026-114 is fully billed.

### Goods receipts (optional three-way match)

| PO | Line | Qty received |
| --- | --- | --- |
| PO-2026-109 | 1, 2 | 10, 10 |
| PO-2026-104 | 1, 2 | 20, 20 |
| PO-2026-105 | 1, 2 | 10, 10 |
| PO-2026-116 | 1 | 15 |
| PO-2026-101 | 1 | 2,000 |
| PO-2026-110 | 1 | 2 |
| PO-2026-114 | 1 | 5,000 |

### Tax rates (India)

| rate | label | valid_from | valid_to |
| --- | --- | --- | --- |
| 0 | Nil / exempt | 2017-07-01 | — |
| 5 | Merit | 2017-07-01 | — |
| 18 | Standard | 2017-07-01 | — |
| 40 | Demerit | 2025-09-22 | — |
| 3 | Special: precious metals | 2017-07-01 | — |
| 12 | Old slab | 2017-07-01 | 2025-09-21 |
| 28 | Old slab | 2017-07-01 | 2025-09-21 |

### Reset

`seed.reset()` drops and recreates all rows above. Runs automatically on startup if the database is empty, and from **Settings → Reset demo data** (type `RESET` to confirm).

---

## 7. Sample invoices (inputs for the demo and tests)

Generated by `backend/scripts/make_seed_and_samples.py` (in the seed kit) with reportlab. Use **three different layouts** (a formal table invoice, a compact modern one, a "small business" one with a logo box and notes) so extraction is genuinely tested. Scans: render page with pypdfium2 at 150 dpi, rotate 1–2°, add light noise and slight blur with Pillow, save as an image-only PDF.

Each sample has an entry in `samples/expected.json` used by the test suite:

| File | Setup | Expected outcome |
| --- | --- | --- |
| `01_happy_deccan.pdf` | V-04, ref "PO-2026-109", 10 desks + 10 drawers, CGST 9% + SGST 9%, date 20 Sep 2026, correct bank | **Approve**, due date capped at 45 days (MSME) |
| `02_happy_brighttech_scan.pdf` | V-02, **scanned**, ref written "PO 105", 10 laptops + 10 backpacks, IGST 18% | **Approve**, "PO 105" normalised to PO-2026-105 |
| `03_edge_inferred_po_acme.pdf` | V-01, **no PO ref**, "ErgoPro Mesh Ergonomic Chair" 20 @ ₹5,000, CGST 9% + SGST 9%, total ₹1,18,000, date 15 Sep 2026 | **Approve**, matched to PO-2026-104 (inferred, high confidence) over PO-2026-117 |
| `04_edge_split_overbill_acme.pdf` | V-01, ref "PO-2026-101", 600 reams @ ₹200 = ₹1,41,600 | **Hold**: exceeds remaining ₹1,18,000; qty 2,100 > 2,000 ordered. Vendor email |
| `05_edge_duplicate_sahyadri_scan.pdf` | V-05, **scanned**, invoice no "42", ₹70,800, date 05 Sep 2026 | **Reject**: duplicate of SPH/INV-0042 |
| `06_edge_bank_changed_brighttech.pdf` | V-02, ref "PO-2026-116", 15 monitors, IGST, **bank 50200099887766** | **Hold (fraud)**: Finance alert, no vendor email |
| `07_extra_quotation_acme.pdf` | Titled "QUOTATION" | **Reject**: not an invoice |
| `08_extra_wrong_split_brighttech.pdf` | V-02, ref PO-2026-116, 5 monitors (₹82,600), but **CGST + SGST** | **Hold**: IGST expected, reissue |
| `09_extra_missing_date_deccan.pdf` | V-04, ref PO-2026-110, 2 conference tables, **no invoice date** | **Hold**: vendor email with response link |
| `10_extra_blocked_quickfix.pdf` | V-06, quotes non-existent PO-2026-099 | **Reject**: vendor blocked |

(Note on 03: Acme is in Telangana like the company, so its tax is CGST 9% + SGST 9%.)

---

## 8. The pipeline framework

Every stage has the same shape, so adding a case is adding a rule.

```python
# pipeline/context.py
@dataclass
class Finding:
    code: str            # "3.2", "6.5" ... matches the design doc case ids
    severity: str        # "pass" | "hold" | "reject" | "info"
    message: str         # plain language for a finance reader
    audience: list[str]  # ["Vendor"], ["AP"], ["Finance","AP"], [] ...
    evidence: dict = field(default_factory=dict)

@dataclass
class RunContext:
    run_id: str
    file_bytes: bytes
    file_hash: str
    company: CompanySettings
    db: Session
    is_scan: bool = False
    extraction: dict | None = None      # stage 2 output
    vendor: Vendor | None = None
    po: PurchaseOrder | None = None
    match_type: str = "None"
    match_confidence: str | None = None
    line_pairs: list = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    halt: bool = False                  # only for "can't continue" (unreadable, not invoice)

@dataclass
class StageResult:
    status: str          # "pass" | "warn" | "fail" | "info"
    message: str         # one line for the timeline
    details: dict        # evidence shown when the stage is expanded
```

```python
# pipeline/runner.py
STAGES = [
    ("Read document", s1_read.run), ("Extract fields", s2_extract.run),
    ("Completeness and maths", s3_validate.run), ("Verify vendor", s4_vendor.run),
    ("Match PO", s5_po_match.run), ("Amounts and quantities", s6_amounts.run),
    ("Duplicates", s7_duplicates.run), ("Tax", s8_tax.run), ("Dates and terms", s9_dates.run),
]

def run_pipeline(ctx, start_at=0):
    for order, (name, fn) in enumerate(STAGES[start_at:], start=start_at + 1):
        t0 = time.monotonic()
        try:
            result = fn(ctx)
        except Exception as e:                       # never crash the run
            ctx.findings.append(Finding("sys", "hold", f"{name} failed: {e}", ["AP"]))
            result = StageResult("fail", f"{name} failed; sent to review", {"error": str(e)})
        pad_to_min_duration(t0)                       # MIN_STAGE_MS for readability
        save_stage(ctx, order, name, result, t0)
        if ctx.halt:
            break
    decision = decide.run(ctx)                        # writes decision + alerts
    save_stage(ctx, 10, "Decision", decision.stage_result, t0)
```

**Principle: run every check, then decide.** Stages add findings; they don't stop the run. Only stage 1–2 can halt (corrupt file, not an invoice, unreadable), because later stages have nothing to check.

When a stage can't do its job because an earlier one failed (for example, no vendor found, so no PO filtering by vendor), it returns `info` with "Skipped: vendor unknown" rather than inventing results.

---

## 9. Stage-by-stage logic with examples

### Stage 1 — Read document (`s1_read.py`)

```python
def run(ctx):
    try:
        pdf = pdfplumber.open(io.BytesIO(ctx.file_bytes))
    except Exception:
        ctx.halt = True
        ctx.findings.append(Finding("1.3", "reject", "The file can't be opened (corrupt or password-protected).", ["AP"]))
        return StageResult("fail", "File can't be opened", {})
    text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    ctx.page_count = len(pdf.pages)
    ctx.text = text
    ctx.is_scan = len(text.strip()) < 50 * ctx.page_count      # almost no text layer
    kind = "Scanned image, will read visually" if ctx.is_scan else "Text PDF"
    return StageResult("pass", f"{kind}, {ctx.page_count} page(s)", {"chars": len(text)})
```

Example: `02_happy_brighttech_scan.pdf` has 12 characters of text on 1 page → `is_scan = True` → timeline shows "Scanned image, will read visually, 1 page".

Document type (invoice vs quotation vs credit note) and multi-invoice splitting are decided in stage 2, because the same LLM call does it.

### Stage 2 — Extract fields (`s2_extract.py`, `llm.py`, `prompts.py`)

**One LLM call** receives the PDF bytes (Gemini reads text and scanned PDFs directly) plus the text layer as a hint, and returns JSON matching this schema:

```python
class ExtractedLine(BaseModel):
    description: str
    hsn: str | None = None
    qty: float | None = None
    unit: str | None = None
    unit_price: float | None = None   # excl. tax
    tax_rate: float | None = None
    amount: float | None = None       # line amount excl. tax

class ExtractedInvoice(BaseModel):
    page_range: list[int]
    vendor_name: str | None
    vendor_gstin: str | None
    invoice_number: str | None
    invoice_date: str | None          # ISO yyyy-mm-dd
    po_reference: str | None          # raw text as printed, anywhere on the page
    currency: str | None
    lines: list[ExtractedLine]
    subtotal: float | None
    cgst: float | None
    sgst: float | None
    igst: float | None
    total: float | None
    tax_inclusive: bool = False
    bank_account: str | None
    ifsc: str | None
    payment_terms_days: int | None
    confidence: dict[str, str]        # field -> "high" | "medium" | "low"

class Extraction(BaseModel):
    doc_type: str                     # "invoice" | "quotation" | "credit_note" | "purchase_order" | "delivery_note" | "statement" | "other"
    invoices: list[ExtractedInvoice]  # more than one if the PDF holds several invoices
    boundaries_clear: bool
```

**Prompt (in `prompts.py`):**

```
You extract data from vendor documents for an accounts payable team in India.
Return JSON that matches the schema exactly. Rules:
1. First classify doc_type. If it is not an invoice, still return what you can read.
2. If the file contains more than one invoice, return one entry per invoice with its page_range.
   Set boundaries_clear=false if you are unsure where one ends.
3. Copy values exactly as printed. Never calculate, guess or fill in a missing value: use null.
4. po_reference: any purchase order reference anywhere on the page (header, notes, line text),
   exactly as written, e.g. "PO 105", "P.O. No: 2026/118". Null if none.
5. Amounts are numbers without currency symbols or commas. Dates in ISO format.
6. If prices include tax (e.g. "incl. GST"), set tax_inclusive=true.
7. confidence: for invoice_number, invoice_date, total, vendor_gstin, bank_account, po_reference,
   say "low" if the text is blurry, partly hidden or ambiguous.
Text layer (may be empty for scans):
<<<TEXT>>>
```

**Adapter with cache and graceful failure:**

```python
def extract(ctx) -> Extraction | None:
    cached = load_cache(ctx.file_hash)                 # fixtures/extractions/<hash>.json or DB
    if cached: return Extraction.model_validate(cached)
    for model in [settings.GEMINI_MODEL, settings.GEMINI_MODEL_FALLBACK]:
        if not model: continue
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[types.Part.from_bytes(data=ctx.file_bytes, mime_type="application/pdf"),
                          PROMPT.replace("<<<TEXT>>>", ctx.text[:20000])],
                config={"response_mime_type": "application/json",
                        "response_schema": Extraction, "temperature": 0})
            data = Extraction.model_validate_json(resp.text)
            save_cache(ctx.file_hash, data.model_dump())
            return data
        except QuotaOrServerError:
            continue
    return None
```

(Confirm exact SDK calls against the current `google-genai` docs; Claude Code can look them up.)

**Stage logic:**

```python
def run(ctx):
    ex = llm.extract(ctx)
    if ex is None:
        ctx.halt = True
        ctx.findings.append(Finding("2.x", "hold", "The invoice couldn't be read automatically. A person needs to enter the details.", ["AP"]))
        return StageResult("fail", "Couldn't read automatically; sent to review", {})
    if ex.doc_type != "invoice":
        severity = "hold" if ex.doc_type == "credit_note" else "reject"
        code = "1.5" if ex.doc_type == "credit_note" else "1.4"
        audience = ["AP"] if code == "1.5" else ["Vendor"]
        ctx.findings.append(Finding(code, severity, f"This document is a {ex.doc_type.replace('_',' ')}, not an invoice.", audience))
        ctx.halt = True
        return StageResult("fail", f"Not an invoice: {ex.doc_type}", {"doc_type": ex.doc_type})
    if len(ex.invoices) > 1:
        if not ex.boundaries_clear:
            ctx.findings.append(Finding("1.7", "hold", "This file seems to contain several invoices. Please send each as a separate PDF.", ["Vendor"]))
            ctx.halt = True
            return StageResult("warn", "Several invoices, unclear boundaries", {})
        spawn_child_runs(ctx, ex.invoices)       # stretch: one new run per invoice (1.6)
        ctx.halt = True
        return StageResult("info", f"Split into {len(ex.invoices)} invoices", {})
    inv = ex.invoices[0]
    if inv.tax_inclusive: back_calculate_tax(inv)          # 2.3
    low = [f for f, c in inv.confidence.items() if c == "low"]
    if low:
        ctx.findings.append(Finding("2.2", "hold", f"Couldn't read {', '.join(low)} reliably; please confirm.", ["AP"], {"fields": low}))
    ctx.extraction = inv.model_dump()
    save_invoice_fields(ctx, inv)
    return StageResult("warn" if low else "pass",
                       f"{len(inv.lines)} line(s), total ₹{fmt(inv.total)}" + (f"; low confidence: {', '.join(low)}" if low else ""),
                       {"fields": inv.model_dump()})
```

**Back-calculating inclusive tax (2.3), example:** line amount ₹1,18,000 "incl. 18% GST" → taxable = 1,18,000 / 1.18 = ₹1,00,000, tax = ₹18,000.

### Stage 3 — Completeness and maths (`s3_validate.py`)

```python
REQUIRED = {"invoice_number": "3.1", "invoice_date": "3.2", "total": "3.3"}
for field, code in REQUIRED.items():
    if not inv[field]:
        add(code, "hold", f"The invoice has no {label(field)}.", ["Vendor"])

lines_sum = sum(l.amount or (l.qty * l.unit_price) for l in lines if computable)
if inv.subtotal and abs(lines_sum - inv.subtotal) > 1:                    # 3.4
    add("3.4", "hold", f"Line items add up to ₹{lines_sum:,.0f} but the subtotal says ₹{inv.subtotal:,.0f} (gap ₹{gap:,.0f}).", ["Vendor"])

tax = (cgst or 0) + (sgst or 0) + (igst or 0)
if subtotal and total and abs(subtotal + tax - total) > 1:                # 3.5
    add("3.5", "hold", f"Subtotal ₹{subtotal:,.0f} + tax ₹{tax:,.0f} ≠ total ₹{total:,.0f}.", ["Vendor"])

if invoice_date and invoice_date > today:                                 # 3.6
    add("3.6", "hold", "The invoice date is in the future.", ["Vendor"])

ctx.bundled = len(lines) == 1 and lines[0].qty is None                    # 3.7
```

Example (3.4): lines 20 × ₹5,000 = ₹1,00,000 and 5 × ₹12,000 = ₹60,000 → ₹1,60,000; printed subtotal ₹1,65,000 → Hold, gap ₹5,000, vendor asked to correct.

### Stage 4 — Verify vendor (`s4_vendor.py`, `utils/gstin.py`)

**GSTIN validation:**

```python
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

def gstin_checksum(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        product = CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    return CHARS[(36 - total % 36) % 36]

def valid_gstin(g: str) -> bool:
    g = (g or "").upper().replace(" ", "")
    return bool(GSTIN_RE.match(g)) and 1 <= int(g[:2]) <= 38 and gstin_checksum(g[:14]) == g[14]

def state_code(g): return g[:2]
def pan(g): return g[2:12]
```

**Logic, in order:**

```python
g = norm(inv.vendor_gstin)
if g and not valid_gstin(g):                                   # 4.3
    add("4.3", "hold", f"The GSTIN on the invoice ({g}) isn't valid.", ["Vendor"])
vendor = db.get(Vendor, tax_id=g) if g else None
if vendor is None:
    by_name = best_name_match(inv.vendor_name)                 # rapidfuzz token_set_ratio ≥ 90
    if by_name and g:                                          # 4.6 known name, different GSTIN
        add("4.6", "hold", f"Name matches {by_name.name}, but the GSTIN doesn't. Possible impersonation.", ["Finance","AP"], fraud=True)
    elif by_name and not g:
        vendor = by_name                                       # no GSTIN printed: fall back to name, note it
        add("4.2", "info", "No GSTIN on invoice; vendor identified by name.", [])
    else:                                                      # 4.4 unknown
        add("4.4", "hold", f"{inv.vendor_name} (GSTIN {g}) isn't an approved vendor.", ["Procurement"])
if vendor and vendor.status == "Blocked":                      # 4.5
    add("4.5", "reject", f"{vendor.name} is blocked.", ["Procurement"])
if vendor and inv.bank_account and digits(inv.bank_account) != digits(vendor.bank_account):   # 4.7
    add("4.7", "hold", f"Bank account on invoice (…{last4(inv)}) differs from the one on file (…{last4(vendor)}). Fraud risk.", ["Finance","AP"], fraud=True)
ctx.vendor = vendor
```

Findings marked `fraud=True` block vendor emails for the whole run (section 13).

Example (4.7): sample 06 prints account 50200099887766; master has 91201004455667 → "Bank account on invoice (…7766) differs from the one on file (…5667). Fraud risk." → Finance alert, no email to the vendor.

### Stage 5 — Match the PO (`s5_po_match.py`, `utils/normalise.py`)

**Step 1: explicit reference, normalised.**

```python
def po_candidates_from_ref(raw: str, invoice_year: int) -> list[str]:
    nums = re.findall(r"\d+", raw or "")
    if len(nums) >= 2 and len(nums[-2]) == 4:            # "2026/118", "PO-2026-118"
        return [f"PO-{nums[-2]}-{int(nums[-1])}"]
    if len(nums) == 1:                                    # "PO 105", "PO118"
        n = int(nums[0])
        return [f"PO-{invoice_year}-{n}", f"PO-{invoice_year-1}-{n}"]
    return []
```

Example: "PO 105" on a 2026 invoice → tries PO-2026-105 → found.

```python
if raw_ref:
    for po_id in po_candidates_from_ref(raw_ref, year):
        po = db.get(PurchaseOrder, po_id)
        if po: break
    if po:
        if vendor and po.vendor_id != vendor.vendor_id:                       # 5.5
            add("5.5", "hold", f"{po.po_id} was issued to {po.vendor.name}, not {vendor.name}.", ["Vendor"])
        elif po.status != "Open":                                             # 5.4
            add("5.4", "hold", f"{po.po_id} is {po.status.lower()}.", ["Procurement"])
        elif inv_date and inv_date < po.po_date:                              # 5.6
            add("5.6", "hold", f"Invoice dated before {po.po_id} was raised.", ["Procurement","AP"])
        ctx.po, ctx.match_type = po, "Explicit"
        return pass_result(f"Matched {po.po_id} (explicit)")
    else:
        not_found_ref = raw_ref                                               # 5.3: fall through to inference
```

**Step 2: filters (no usable reference).**

```python
cands = open POs for vendor
log = []
for po in all POs:
    if po.vendor_id != vendor.vendor_id: log.append((po, "Vendor")); continue
    if po.status != "Open":               log.append((po, "Status")); continue
    remaining = po_remaining_paise(po)
    if total > remaining + allowed_diff(remaining): log.append((po, f"Balance: only ₹{remaining}")); continue
    if inv_date < po.po_date:             log.append((po, "Date: raised after invoice")); continue
    survivors.append(po)
```

The elimination log goes into `details` so the UI can show the table from the design doc.

**Step 3: scoring (only if more than one survivor, or to report confidence).**

```python
def score(po, inv_lines, total, inv_date):
    # Line items (50): each invoice line is paired with its best PO line.
    # A pair only counts if description similarity >= 0.6 (the LLM judges this).
    pts = []
    for il in inv_lines:
        best = max(po.lines, key=lambda pl: sim(il.description, pl.description))
        s = sim(il.description, best.description)
        if s < 0.6: pts.append(0); continue
        qty_ok = il.qty is not None and il.qty <= best.qty - invoiced_qty(po.po_id, best.line_no)
        price_ok = il.unit_price is not None and within_tol(il.unit_price, best.unit_price)
        pts.append(0.5 * s + 0.25 * qty_ok + 0.25 * price_ok)
    line_score = 50 * (sum(pts) / len(pts)) if pts else 0

    remaining = po_remaining(po)
    amount_score = 30 * min(total, remaining) / max(total, remaining)

    days = (inv_date - po.po_date).days
    date_score = 20 * max(0, 1 - days / 60)
    return round(line_score + amount_score + date_score, 1)
```

**Description similarity (`sim`)** is one batched LLM call per run: send every invoice line and every candidate PO line, get back a matrix of 0–1 scores as JSON. If the LLM is unavailable, fall back to `rapidfuzz.fuzz.token_set_ratio / 100`, and mark the match confidence one level lower.

**Worked example with sample 03** (invoice: 20 × "ErgoPro Mesh Ergonomic Chair" @ ₹5,000, total ₹1,18,000, dated 15 Sep 2026):

Filters: all three open Acme POs survive. PO-2026-104 and PO-2026-117 obviously fit, and PO-2026-101 also passes the balance filter because exactly ₹1,18,000 remains on it. This is why scoring exists: filters alone can't tell copier paper from chairs.

| Signal | PO-2026-104 | PO-2026-117 | PO-2026-101 |
| --- | --- | --- | --- |
| Description similarity | 0.9 (mesh ergonomic chair) | 0.4 (standard chair) → pair doesn't count | 0.0 (copier paper) → doesn't count |
| Line score (50) | 50 × (0.45 + 0.25 + 0.25) = 47.5 | 0 | 0 |
| Amount fit (30) | 30 × 1,18,000 / 1,48,680 = 23.8 | 30 × 1,18,000 / 1,18,000 = 30.0 | 30.0 |
| Date (20), days after PO | 26 days → 11.3 | 5 days → 18.3 | 105 days → 0 |
| **Total** | **82.6** | **48.3** | **30.0** |

Top 82.6 ≥ 70 and ahead by 34.3 ≥ 20 → **Matched PO-2026-104 (inferred, high confidence)**. The timeline shows the table, and the key sentence: *"PO-2026-117 fits the amount exactly, but it's for 25 standard chairs at ₹4,000; the invoice is for 20 ergonomic mesh chairs at ₹5,000."*

**Decision thresholds:**

| Result | Outcome | Finding |
| --- | --- | --- |
| Top ≥ 70 and gap ≥ 20 | Match, "Inferred, high" | 5.7 pass (plus 5.3 hold if a wrong ref was printed) |
| Top ≥ 70, gap < 20 | Hold, both shown | 5.8 → AP |
| Top < 70 | Hold | 5.9 → Vendor (ask for PO), Procurement |
| No survivors | Hold | 5.9 |
| Lines match two different POs | Hold | 5.10 → AP |
| Bundled invoice (no qty) | Line score = 0, so usually < 70 → Hold | via 5.9 |

Keep thresholds and weights in `config.py`, and tune them with the test suite.

### Stage 6 — Amounts and quantities (`s6_amounts.py`, `utils/money.py`)

```python
def allowed_diff(expected_paise):
    return min(company.tolerance_pct * expected_paise, company.tolerance_abs_paise)
```

Example: expected ₹1,00,000 → 2% = ₹2,000 (under the ₹5,000 cap) → allowed ₹2,000. Expected ₹5,00,000 → 2% = ₹10,000 → capped at ₹5,000.

```python
remaining = po_remaining(po)                   # excludes this run
if total > remaining + allowed_diff(remaining):                          # 6.5
    add("6.5", "hold",
        f"Only ₹{remaining:,} remains on {po.po_id}; this invoice is ₹{total:,}.",
        ["Vendor"], {"previous_invoices": ledger_rows(po)})
for pair in line_pairs:                                                   # paired in stage 5
    already = invoiced_qty(po.po_id, pair.po_line.line_no)
    if pair.inv.qty + already > pair.po_line.qty:                        # 6.6
        add("6.6", "hold", f"{pair.inv.description}: {already + pair.inv.qty:g} invoiced in total vs {pair.po_line.qty:g} ordered.", ["Vendor"])
    if abs(pair.inv.unit_price - pair.po_line.unit_price) > allowed_diff(pair.po_line.unit_price):   # 6.7
        add("6.7", "hold", f"{pair.inv.description}: ₹{pair.inv.unit_price:,} per unit vs ₹{pair.po_line.unit_price:,} on the PO.", ["Vendor"])
for il in unpaired_lines:                                                 # 6.8
    add("6.8", "hold", f"'{il.description}' isn't on {po.po_id}.", ["Vendor","Procurement"])
# optional three-way (section 16)
```

Example (sample 04): PO-2026-101 total ₹4,72,000, approved so far ₹3,54,000 → remaining ₹1,18,000; invoice ₹1,41,600 → over by ₹23,600 (allowed ₹2,360) → **6.5 Hold**. Quantity: 1,500 already + 600 = 2,100 > 2,000 → **6.6 Hold**. One vendor email lists both.

### Stage 7 — Duplicates (`s7_duplicates.py`)

```python
def core_number(inv_no):              # "SPH/INV-0042" -> "42", "42" -> "42", "INV-0042" -> "42"
    groups = re.findall(r"\d+", inv_no or "")
    return str(int(groups[-1])) if groups else None

def norm_full(inv_no):                # "SPH/INV-0042" -> "SPHINV0042"
    return re.sub(r"[^A-Z0-9]", "", (inv_no or "").upper())
```

Checks against previous runs of the **same vendor**:

```python
if prior_with_same_file_hash:                                              # 7.1
    add("7.1", "reject", f"This exact file was already processed as {prior.run_id}.", ["AP"])
for prior in same_vendor_invoices:
    same_number = norm_full(prior.no) == norm_full(no) or core_number(prior.no) == core_number(no)
    if same_number and (prior.total == total or prior.date == date):      # 7.2 / 7.3
        sev = "reject" if prior.decision == "Approve" else "hold"
        add("7.2", sev, f"Same as invoice {prior.invoice_no} received on {prior.date} ({prior.run_id}).", ["Vendor","AP"])
    elif prior.total == total and abs((prior.date - date).days) <= 30:    # 7.4
        add("7.4", "hold", f"Same amount as {prior.invoice_no} from {prior.date}. Possible duplicate.", ["AP"])
```

Example (sample 05): invoice no "42", ₹70,800, 05 Sep 2026, Sahyadri. Prior: "SPH/INV-0042", same total, same date, Approved → core numbers both "42" → **Reject**, linked to the original. A legitimate monthly rent invoice (7.5) passes because numbers differ and the billing period differs.

### Stage 8 — Tax (`s8_tax.py`, `tax/`)

```python
def get_tax_model(country):
    return {"IN": IndiaGST()}.get(country, ManualTax())
```

`IndiaGST.check(ctx)`:

```python
if vendor.country != company.country:                                     # import
    if tax_total > 0:
        add("8.7", "hold", "A foreign vendor shouldn't charge GST; Indian tax is paid via customs or reverse charge.", ["Vendor"])
    else:
        add("8.x", "info", "Import: IGST payable separately (customs or reverse charge).", [])
    return
same_state = vendor.tax_id[:2] == company.state_code
expected_split = "CGST+SGST" if same_state else "IGST"
actual_split = "CGST+SGST" if (cgst or sgst) else ("IGST" if igst else "None")
if actual_split != expected_split:                                        # 8.3
    add("8.3", "hold", f"Vendor is in state {vendor.tax_id[:2]} and we are in {company.state_code}: {expected_split} applies, but the invoice charges {actual_split}. Please reissue.", ["Vendor"])
for pair in line_pairs:
    rate = pair.inv.tax_rate
    if not rate_valid_on(rate, inv_date):                                 # 8.5
        add("8.5", "hold", f"{rate}% isn't a valid GST rate on {inv_date} (12% and 28% ended on 21 Sep 2025).", ["Vendor"])
    elif rate != pair.po_line.tax_rate:                                   # 8.4
        add("8.4", "hold", f"{pair.inv.description}: {rate}% on the invoice vs {pair.po_line.tax_rate}% on the PO.", ["Vendor"])
expected_tax = sum(taxable(l) * l.tax_rate / 100 for l in lines)
if abs(expected_tax - tax_total) > 1:                                     # 8.6
    add("8.6", "hold", f"Tax should be ₹{expected_tax:,.0f}, invoice shows ₹{tax_total:,.0f}.", ["Vendor"])
if same_state and cgst and sgst and abs(cgst - sgst) > 1:
    add("8.6", "hold", "CGST and SGST should be equal halves.", ["Vendor"])
```

`ManualTax.check`: compare the invoice's rate with `po_line.tax_rate` (declared by the user on the PO); message ends with "(declared on PO; not independently verified)".

Example (sample 08): BrightTech is state 29, company is 36 → IGST expected; invoice shows CGST 9% + SGST 9% → **8.3 Hold**, vendor asked to reissue. Totals are correct, which is exactly why a tired human would miss it.

### Stage 9 — Dates and terms (`s9_dates.py`)

```python
terms = po.payment_terms_days if po else 30
if vendor and vendor.msme and terms > 45:
    terms = 45; note("9.5", "MSME vendor: due date capped at 45 days.")
due = inv_date + timedelta(days=terms)                                     # 9.1
if (today - inv_date).days > 180: add("9.2", "hold", "Invoice is over 180 days old.", ["AP"])
if inv.payment_terms_days and po and inv.payment_terms_days != po.payment_terms_days:
    note("9.3", f"Invoice says {inv.payment_terms_days} days; PO terms ({po.payment_terms_days} days) apply.")
if due < today: add("9.4", "info", "Already overdue: pay urgently.", ["AP"])
ctx.due_date = due
```

Example (sample 01): Deccan is MSME, PO terms 60 days → capped at 45 → invoice 20 Sep 2026 → due **04 Nov 2026**.

### Decision (`decide.py`)

```python
sev = [f.severity for f in ctx.findings]
decision = "Reject" if "reject" in sev else "Hold" if "hold" in sev else "Approve"
status = {"Reject": "rejected", "Hold": "needs_review", "Approve": "approved"}[decision]
reasons = [f.message for f in ctx.findings if f.severity in ("hold", "reject")] or \
          [f"Vendor verified", f"Matched {po.po_id} ({ctx.match_type.lower()})", "Amounts within tolerance",
           "No duplicate found", f"{expected_split} verified"]
headline = {
  "Approve": f"Pay ₹{total:,} to {vendor.name} by {due:%d %b %Y}.",
  "Hold":    f"On hold: {len(reasons)} issue(s) need attention.",
  "Reject":  f"Rejected: {reasons[0]}",
}[decision]
alerts.build_and_send(ctx, decision)
```

A Hold always goes to the Review queue (`needs_review`), so a human closes every open item.

---

## 10. Alerts and email (`alerts.py`)

**Grouping:** one alert per audience per run, listing every finding for that audience.

```python
by_audience = defaultdict(list)
for f in findings:
    for a in f.audience: by_audience[a].append(f)
fraud = any(getattr(f, "fraud", False) for f in findings)
if fraud: by_audience.pop("Vendor", None)          # never email the vendor on a fraud hold
```

**Recipients:** every alert is delivered to `OWNER_EMAIL`; the **intended** recipient is stored and printed at the top of the email.

| Audience | intended_for | Subject prefix |
| --- | --- | --- |
| Vendor | "Acme Supplies Private Limited (accounts)" | `[InvoiceIQ → Vendor: Acme Supplies]` |
| AP | "Nimbus Retail AP team" | `[InvoiceIQ → AP]` |
| Procurement | "Nimbus Retail Procurement" | `[InvoiceIQ → Procurement]` |
| Finance | "Nimbus Retail Finance" | `[InvoiceIQ → Finance · Fraud check]` |

Tip: create a Gmail filter on `[InvoiceIQ` to label them, so they're easy to show in the video.

**Vendor email template (Hold):**

```
Intended for: Acme Supplies Private Limited (accounts)

Hello Acme Supplies team,

We've received invoice ACME/2026/0417 dated 18 Sep 2026 for ₹1,41,600 against PO-2026-101.
We can't process it yet because:

  1. Only ₹1,18,000 remains on PO-2026-101; this invoice is ₹1,41,600.
  2. Copier paper: 2,100 reams invoiced in total vs 2,000 ordered.

Please send a corrected invoice using this secure link (valid 7 days):
{BASE_URL}/respond/{token}

Thank you,
Accounts Payable, Nimbus Retail Pvt Ltd
```

**Finance fraud template (sample 06):**

```
Intended for: Nimbus Retail Finance

Possible payment fraud on invoice BT/26/0917 (₹2,47,800, PO-2026-116, BrightTech Solutions).
The bank account on the invoice (…7766) differs from the account on file (…5667).
Everything else matches the PO.

Do not reply to the email that sent this invoice. Verify the change by calling BrightTech
on the phone number in the vendor master. Clear or reject this hold in InvoiceIQ:
{BASE_URL}/review/{run_id}
```

**Sending (Resend over HTTPS; free hosts often block SMTP):**

```python
import resend
resend.api_key = settings.RESEND_API_KEY

def send(alert):
    if alert.audience == "Vendor" and not settings.VENDOR_AUTO_SEND:
        alert.status = "Drafted"; return            # AP clicks "Send" in the Outbox
    try:
        resend.Emails.send({"from": settings.EMAIL_FROM, "to": [settings.OWNER_EMAIL],
                            "subject": alert.subject, "text": alert.body})
        alert.status, alert.sent_at = "Sent", now()
    except Exception as e:
        alert.status = "Failed"; log(e)             # never fails the run
```

Free limit is 100 emails a day; one run sends at most 3–4, so the demo is safe.

**Vendor response link:** `token = secrets.token_urlsafe(24)`, stored on the alert with a 7-day expiry, single use. `/respond/{token}` (a React page) shows the invoice summary and the listed issues, and lets the vendor upload a corrected PDF or fill a missing field (e.g. date). Submitting creates a **new run** with `parent_upload_id` = original run, marks the original `waiting_on_vendor → superseded`, and streams normally. Because the recipient is you, you'll click the link from your own inbox in the demo.

---

## 11. Human review (`routers/runs.py` → `POST /api/runs/{id}/review`)

| Action | Body | What happens |
| --- | --- | --- |
| `confirm` | `{fields: {...corrections}}` | Save corrections to `extraction`, log a Review with before/after, resume the pipeline from stage 3 in a background task; the Process page re-streams the new stages |
| `pick_po` | `{po_id}` | Set PO, match_type "Explicit (reviewer)", resume from stage 6 |
| `override` | `{reason}` | Only allowed if no fraud finding (else 403 unless role = Finance); decision = Approve, reason logged |
| `send_to_vendor` | `{reason, note}` | Build vendor alert with that reason, status `waiting_on_vendor` |
| `reject` | `{reason}` | Decision = Reject |

Resuming means clearing `run_stages` rows from that stage onward, clearing findings from those stages, and calling `run_pipeline(ctx, start_at=N)`.

---

## 12. API (`routers/`)

| Method | Path | Returns |
| --- | --- | --- |
| POST | `/api/runs` | multipart `file` **or** `sample_name` → `{run_id}`; enforces `MAX_RUNS_PER_DAY` |
| GET | `/api/runs/{id}/stream` | SSE events `stage`, `decision`, `done` |
| GET | `/api/runs?status=&vendor=&q=` | list for dashboard |
| GET | `/api/runs/{id}` | invoice, lines, stages, findings, alerts, reviews, matched PO with lines |
| GET | `/api/runs/{id}/file` | the original PDF (for preview) |
| POST | `/api/runs/{id}/review` | see section 11 |
| GET | `/api/stats` | KPIs + chart series |
| GET/POST | `/api/pos`, PATCH `/api/pos/{id}` | list with remaining balance, create, close/edit |
| GET/POST | `/api/vendors` | list, add (with duplicate GSTIN / bank checks) |
| GET | `/api/tax-rates?country=IN&on=2026-09-24` | valid rates for dropdowns |
| GET | `/api/alerts`, POST `/api/alerts/{id}/send` | Outbox, send drafted |
| GET/POST | `/api/respond/{token}` | vendor response page data, submit correction |
| GET | `/api/samples` | sample list with descriptions and expected outcome |
| POST | `/api/admin/reset` | body `{confirm: "RESET"}` |
| POST | `/api/admin/test-suite` | runs every sample, returns expected vs actual |
| GET | `/api/health` | `{ok: true}` for Render + UptimeRobot |

**SSE endpoint:**

```python
@router.get("/api/runs/{run_id}/stream")
async def stream(run_id: str):
    async def events():
        sent = 0
        while True:
            with SessionLocal() as db:
                rows = db.query(RunStage).filter(RunStage.run_id == run_id,
                        RunStage.stage_order > sent).order_by(RunStage.stage_order).all()
                run = db.get(Invoice, run_id)
            for r in rows:
                yield f"event: stage\ndata: {json.dumps(stage_dict(r))}\n\n"
                sent = r.stage_order
            if run.status != "running" and sent >= last_stage_order(run):
                yield f"event: decision\ndata: {json.dumps(decision_dict(run))}\n\n"
                yield "event: done\ndata: {}\n\n"
                return
            yield ": keepalive\n\n"
            await asyncio.sleep(0.4)
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

**Frontend side:**

```ts
const es = new EventSource(`/api/runs/${runId}/stream`);
es.addEventListener("stage", e => setStages(s => [...s, JSON.parse((e as MessageEvent).data)]));
es.addEventListener("decision", e => setDecision(JSON.parse((e as MessageEvent).data)));
es.addEventListener("done", () => es.close());
```

---

## 13. KPIs and monitoring (`/api/stats`)

| KPI | Formula | Why the buyer cares |
| --- | --- | --- |
| Invoices processed | count of non-seed runs | Volume |
| Touchless rate | approved with no review ÷ processed | How much work disappears |
| Held / Rejected | counts by decision | Exception load |
| Money protected | ₹ total of runs rejected as duplicate + ₹ over-billing blocked (invoice − remaining) + ₹ of fraud holds | ROI in rupees |
| Time saved | processed × 8 min (assumption shown on the card) | Hours back to the AP team |
| Avg processing time | mean(finished_at − created_at) | Speed |
| Top hold reasons | count of findings by code | What to fix with vendors |
| Health | share of runs with low-confidence extraction, LLM failures, avg stage duration | Monitoring: spots a vendor changing format |

---

## 14. Frontend design

**Look:** light, calm, finance-grade. Inter font, white cards on a very light grey page, one blue accent. Decision colours only for decisions: green Approve, amber Hold, red Reject. Left sidebar: Process, Review (with count badge), Dashboard, Purchase orders, Vendors, Outbox, Tests, Settings. Top-right: role selector (Procurement / AP clerk / Finance).

**Process page:**
- Left column: dropzone ("Drop an invoice PDF"), below it "Try a sample" list with short descriptions and a small tag for the expected scenario, then a PDF preview (`<iframe src="/api/runs/{id}/file">`).
- Right column: **StageTimeline**. Each stage is a row that slides in (Framer Motion) with an icon (check / alert / x / info), stage name, one-line message and duration. Click to expand the evidence: extracted field table, PO elimination table, score table, ledger, tax comparison.
- Bottom: **DecisionCard** (big Approve/Hold/Reject pill + headline + reasons), **CompareTable** (invoice line vs PO line, mismatched cells highlighted amber), **AlertCards** (audience, intended for, subject, Sent/Drafted, "View" and "Send").

**Review page:** list of held runs; detail shows the PDF on the left and the editable fields on the right, low-confidence fields outlined amber, action buttons with reason inputs.

**Dashboard:** KPI cards row, "Decisions over time" stacked bar chart, "Top hold reasons" bar chart, runs table with filters; clicking a row opens the stage trail in a side panel.

**POs page:** table with a remaining-balance bar per PO and expandable invoices billed against it; "Create PO" opens the form (vendor dropdown + "Add new vendor", date, terms, department, line items table with add/remove rows, live totals and tax type).

**Tests page:** "Run all samples" → table of sample, expected, actual, pass/fail, link to the run.

**Respond page (`/respond/:token`):** public, minimal, shows the issues and an upload box or a single missing field.

Copy style: sentence case, verbs on buttons ("Send to vendor", "Confirm and continue"), money always as ₹ with Indian grouping (`Intl.NumberFormat("en-IN")`).

---

## 15. Deployment (all free)

**Dockerfile (multi-stage):**

```dockerfile
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=web /web/dist ./static
ENV PORT=8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
```

`main.py` mounts `./static` and returns `index.html` for any non-`/api` path, so React routes like `/respond/abc` work on refresh.

**Steps:**

1. **Neon:** create project → copy the connection string → change the prefix to `postgresql+psycopg://` and keep `?sslmode=require`.
2. **Google AI Studio:** create an API key; note the current Flash-Lite model ID and your daily quota.
3. **Resend:** sign up with nvmanishankar@gmail.com → create API key. Keep `from` as `onboarding@resend.dev`.
4. **GitHub:** push the repo (without `.env`).
5. **Render:** New → Web Service → connect repo → Runtime **Docker** → Instance type **Free** → add all env vars (set `BASE_URL` to the Render URL after the first deploy, then redeploy) → Health check path `/api/health`.
6. First boot auto-seeds the empty Neon database.
7. **Test on the live URL:** run all samples from the Tests page; confirm emails arrive.
8. **UptimeRobot (optional):** HTTP monitor on `/api/health` every 5 minutes, so the app is awake when the panel opens it. One free Render service running all month stays within the free instance hours.

---

## 16. Optional: light three-way match

Add stage 6b when the core is done:

```python
received = goods_received_qty(po.po_id, line_no)
if already_invoiced + inv_qty > received:
    add("6.10", "hold", f"{desc}: {already_invoiced + inv_qty:g} invoiced but only {received:g} received.", ["Procurement","Vendor"])
```

Demo idea: edit PO-2026-104's receipt to 15 chairs in the PO register, re-run sample 03 → Hold "20 invoiced but only 15 received".

---

## 17. Testing

1. **Unit tests (pytest, no network):** GSTIN checksum, PO ref normalisation ("PO 105", "P.O. No: 2026/118"), invoice core numbers, tolerance, remaining balance, GST split rules, scoring on the section 9 example, decision precedence.
2. **Pipeline tests with cached extractions:** `fixtures/extractions/<hash>.json` for every sample, so the full pipeline runs in tests without calling Gemini. Assert each sample's expected decision and key finding codes.
3. **Tests page in the app:** same assertions against the live system, one click. Run it after every deploy and before recording the video.

Create the fixtures by running each sample once through the real LLM, reviewing the JSON by eye, fixing anything wrong, and committing it.

---

## 18. Build order with Claude Code

### How to work with Claude Code

- Put the **design doc** and **this guide** in the repo root (`docs/`), and create `CLAUDE.md` (below). Claude Code reads it every session.
- One phase per session. Start each with: *"Read CLAUDE.md and docs/InvoiceIQ_Build_Guide.md section X. Plan first, then implement."* Use plan mode for anything larger than one file.
- Ask for tests with every phase. Run them yourself.
- Commit after each phase: `git commit -m "phase 4: extraction with cache"`.
- If Claude Code proposes something that contradicts the guide (a new library, a different flow), ask why before accepting.

### CLAUDE.md

```markdown
# InvoiceIQ

AP invoice processing: PDF → extract → match PO → checks → Approve/Hold/Reject, with a live stage view.
Spec: docs/InvoiceIQ_Solution_Design_PS1.md. How-to: docs/InvoiceIQ_Build_Guide.md.

## Non-negotiables
- AI reads, rules decide. The LLM only extracts and scores text similarity. Every decision is Python rules.
- Run every check, then decide. Stages append Findings; only stages 1-2 may halt.
- Never guess missing values. Null + a finding.
- Money in integer paise. Display ₹ with en-IN grouping.
- Every finding has a case code from the design doc (e.g. "6.5") and a plain-English message for a finance reader.
- LLM calls: max 2 per run, cached by file hash, graceful fallback. Never crash a run on an LLM error.
- All emails go to OWNER_EMAIL via Resend; store the intended recipient. Never email the vendor on a fraud finding.
- Free tools only. No new paid services.

## Stack
FastAPI, SQLAlchemy 2, SQLite locally / Postgres (Neon) live, google-genai, pdfplumber, pypdfium2, rapidfuzz, resend.
React + Vite + TS, Tailwind, shadcn/ui, Framer Motion, Recharts, TanStack Query.

## Commands
backend: `uvicorn app.main:app --reload` · tests: `pytest -q` · CLI: `python scripts/run_cli.py samples/01_happy_deccan.pdf`
frontend: `npm run dev` (proxy /api to :8000) · build: `npm run build`
```

### Phases

| # | Phase | Prompt to Claude Code (short form) | Done when |
| --- | --- | --- | --- |
| 0 | Accounts | (by hand) Create Neon, AI Studio key, Resend, GitHub repo, Render account with nvmanishankar@gmail.com | Keys in local `.env` |
| 1 | Skeleton | "Create the repo layout from section 3, FastAPI app with /api/health, Vite React app with Tailwind + shadcn, dev proxy, Dockerfile from section 15." | Both dev servers run |
| 2 | Data | "Implement models.py (section 5), db.py for SQLite/Postgres, seed.py with the exact seed data in section 6 including GSTIN checksum generation, auto-seed on empty DB, reset. Unit-test po_remaining for PO-2026-101 = ₹1,18,000." | Tests pass |
| 3 | Samples | Already generated in the seed kit (`backend/scripts/make_seed_and_samples.py`). Prompt: "Load backend/app/seed_data/*.json in seed.py; write a test that runs make_seed_and_samples.py and checks all 10 PDFs exist." | Seed loads; PDFs open |
| 4 | Extraction | "Implement llm.py and stage 1–2 exactly as section 9 with cache by hash, fallback model, and graceful failure. Add run_cli.py printing stages." | Sample 01 and 02 extract correctly; fixtures saved |
| 5 | Rules | "Implement stages 3–9 and decide.py as section 9. Unit-test each case code used by samples 01–06." | CLI gives expected decisions for 01–06 |
| 6 | API + SSE | "Implement runs router, background pipeline, SSE stream (section 12), samples endpoint, run file endpoint, daily cap." | curl shows stage events |
| 7 | Process page | "Build the Process page (section 14): dropzone, sample picker, PDF preview, animated StageTimeline with expandable evidence, DecisionCard, CompareTable." | Happy path streams live in the browser |
| 8 | Edge cases | "Verify samples 03–06 end to end in the UI; render the elimination and score tables for 03, ledger for 04, linked original for 05, fraud banner for 06." | All four behave as expected |
| 9 | Deploy early | "Prepare for Render: static serving, SPA fallback, env config." Then deploy by hand (section 15). | Live URL runs samples 01–06 |
| 10 | Review + alerts | "Implement review actions (section 11), alerts with grouping and templates (section 10), Resend sending, Outbox page, Review page." | Hold → confirm/resume works; emails arrive |
| 11 | Dashboard | "Implement /api/stats and the Dashboard (sections 13–14)." | KPIs and charts show real runs |
| 12 | POs, vendors, settings | "PO register with remaining bars, Create PO form, Add vendor with checks, Settings with reset and role selector." | Create PO → invoice matches it |
| 13 | Tests page | "Implement /api/admin/test-suite and the Tests page (section 17)." | 10/10 pass on the live URL |
| 14 | Rehearse + video | (by hand) Reset data, run the demo script, record on Loom | Video ≤ 5 min |
| 15 | Stretch | Vendor response link, samples 07–10 polish, three-way match (section 16), PDF splitting, multi-country form, investigator agent | Only after 14 |

**Deploy at phase 9, not at the end.** Hosting problems found on the last night are the most common way these builds fail.

---

## 19. Demo checklist (day of recording and interview)

- [ ] Open the live URL 10 minutes early (or rely on UptimeRobot).
- [ ] Settings → Reset demo data.
- [ ] Tests page: all pass.
- [ ] Gmail open in another tab, filtered to `[InvoiceIQ`.
- [ ] Order: 01 happy → 03 inferred PO → 06 bank changed → Dashboard → close a PO and re-run → (live interview extras: 04, 05, 08, 09 with response link).
- [ ] If the LLM quota is exhausted, cached samples still run instantly; say so if asked.
- [ ] One sentence ready for each "why" in the design doc's interview section, plus: "Why Gemini? Free tier for a zero-cost live demo; the LLM sits behind one adapter, so Claude or any model can replace it."
