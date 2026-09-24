# InvoiceIQ

**Live demo:** _coming soon (Render URL goes here)_

InvoiceIQ is an accounts-payable assistant, built for the Zamp AI Solutions Associate case study (PS-1). You give it a vendor invoice PDF, text or scanned. It extracts the fields with an LLM, then runs Python rules that check the vendor, match the purchase order (explicit or inferred), check amounts and remaining PO balance, catch duplicates, and validate Indian GST and payment terms. It ends with an explainable **Approve / Hold / Reject** decision and routed email alerts, and you can watch each stage live in the browser. The AI reads; the rules decide.

## Assumptions

From the [solution design](docs/InvoiceIQ_Solution_Design_PS1.md#assumptions):

1. The buying company is in India (Hyderabad, Telangana, state code 36); vendors are Indian unless marked otherwise.
2. Currency is INR; matching is always done in the PO's currency.
3. Two-way match only (invoice vs PO).
4. POs come from the company's ERP; the Create PO form stands in for it. POs are never extracted from PDFs, because the reference data must be exact.
5. Tolerance is ±2% of the amount, capped at ₹5,000.
6. Only approved invoices consume a PO's balance.
7. A wrong confident decision is worse than a Hold, so ambiguity always goes to a human.
8. Tax rates are configuration (a table), not code.
9. Open question sent to the hiring coordinator: India-based setup, or US (USD, sales tax)? Building India meanwhile, with tax as a separate module.

## Run locally

Needs Python 3.11 and Node 20.19+.

1. Copy the env file. SQLite works with no changes; the samples run offline from cached extractions, so API keys are only needed for new PDFs and real emails.

   ```bash
   cp .env.example .env
   ```

2. Start the backend on http://localhost:8000. It creates the tables and seeds the demo data on first start.

   ```bash
   cd backend
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements-dev.txt
   uvicorn app.main:app --reload
   ```

3. In a second terminal, start the frontend on http://localhost:5173. It proxies `/api` to :8000.

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

4. Optional checks, from `backend/`:

   ```bash
   pytest -q                                            # test suite, offline
   python scripts/run_cli.py samples/01_happy_deccan.pdf  # one sample in the terminal, throwaway DB
   python scripts/check_db.py                           # DATABASE_URL ready? tables, seed, sample 01
   ```

## Deploy

Production is one Docker image on Render: the React build is served by FastAPI (see `Dockerfile`), and the database is Neon Postgres. Set `DATABASE_URL` to the Neon string with the `postgresql+psycopg://` prefix and `?sslmode=require`, add the other variables from `.env.example`, and use `/api/health` as the health check. Steps: [build guide section 15](docs/InvoiceIQ_Build_Guide.md#15-deployment-all-free).

## Docs

- [docs/InvoiceIQ_Solution_Design_PS1.md](docs/InvoiceIQ_Solution_Design_PS1.md): what and why
- [docs/InvoiceIQ_Build_Guide.md](docs/InvoiceIQ_Build_Guide.md): how (stack, data model, pipeline, API, UI, build phases)
- [docs/SEED_KIT_README.md](docs/SEED_KIT_README.md): seed data and sample invoices
