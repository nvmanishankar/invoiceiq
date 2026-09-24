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
