# InvoiceIQ

InvoiceIQ is an accounts-payable assistant, built for the Zamp AI Solutions Associate case study (PS-1). You give it a vendor invoice PDF, text or scanned. It extracts the fields with an LLM, then runs Python rules that check the vendor, match the purchase order (explicit or inferred), check amounts and remaining PO balance, catch duplicates, and validate Indian GST and payment terms. It ends with an explainable **Approve / Hold / Reject** decision and routed email alerts, and you can watch each stage live in the browser. The AI reads; the rules decide.

## Run locally

Needs Python 3.11 and Node 20+.

```bash
cp .env.example .env            # fill in keys later; SQLite works with no changes

# backend (http://localhost:8000). Auto-seeds the demo data on first start
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload

# tests (from backend/)
pytest -q

# frontend (http://localhost:5173, proxies /api to :8000)
cd frontend
npm install
npm run dev
```

Production runs as one Docker image on Render: React is built and served by FastAPI (see `Dockerfile`).

## Docs

- [docs/InvoiceIQ_Solution_Design_PS1.md](docs/InvoiceIQ_Solution_Design_PS1.md): what and why
- [docs/InvoiceIQ_Build_Guide.md](docs/InvoiceIQ_Build_Guide.md): how (stack, data model, pipeline, API, UI, build phases)
- [docs/SEED_KIT_README.md](docs/SEED_KIT_README.md): seed data and sample invoices
