# InvoiceIQ seed kit

Drop these folders into the repo root. They match sections 6 and 7 of `InvoiceIQ_Build_Guide.md`.

```
backend/
├── app/seed_data/          # load these in seed.py (company, vendors, tax rates, POs, ledger, goods receipts)
├── samples/                # 10 invoice PDFs + expected.json
└── scripts/make_seed_and_samples.py   # regenerates everything above
```

Regenerate any time: `python backend/scripts/make_seed_and_samples.py`
(needs `reportlab pypdfium2 Pillow numpy`; add them to a dev requirements file, not the production image).

## Conventions

- Money is **integer paise** (Rs 1 = 100). `118000 rupees` is stored as `11800000`.
- Dates are ISO strings (`2026-09-20`). Sample 09 has `invoice_date: null` on purpose.
- Every email address is `nvmanishankar@gmail.com`.
- All GSTINs have valid checksums (the generator computes the last character).
- Ledger rows (`SEED-0001..0003`) are invoices approved **before** the app existed. Load them into `invoices` with `is_seed = true` and their lines into `invoice_lines`. They make PO-2026-101 partly billed and PO-2026-114 fully billed. Hide `is_seed` rows from dashboard KPIs.

## PO balances after seeding

| PO | Vendor | Status | Total (Rs) | Remaining (Rs) | Used by |
| --- | --- | --- | --- | --- | --- |
| PO-2026-101 | Acme (V-01) | Open | 4,72,000 | 1,18,000 | Sample 04 (overbill), decoy in 03 |
| PO-2026-104 | Acme (V-01) | Open | 1,48,680 | 1,48,680 | Sample 03 (correct inferred match) |
| PO-2026-117 | Acme (V-01) | Open | 1,18,000 | 1,18,000 | Sample 03 (decoy: exact amount) |
| PO-2026-105 | BrightTech (V-02) | Open | 7,81,160 | 7,81,160 | Sample 02 |
| PO-2026-116 | BrightTech (V-02) | Open | 2,47,800 | 2,47,800 | Samples 06, 08 |
| PO-2026-108 | Zenith (V-03) | Open | 3,54,000 | 3,54,000 | Spare (create a live invoice against it) |
| PO-2026-109 | Deccan (V-04) | Open | 2,65,500 | 2,65,500 | Sample 01 |
| PO-2026-110 | Deccan (V-04) | Open | 82,600 | 82,600 | Sample 09 |
| PO-2026-112 | Sahyadri (V-05) | Closed | 94,400 | — | Closed-PO what-if |
| PO-2026-114 | Sahyadri (V-05) | Open | 70,800 | 0 | Sample 05 (duplicate) |

## Samples

| File | Layout | Scan | Expected | Must-have finding codes |
| --- | --- | --- | --- | --- |
| 01_happy_deccan | A formal | No | Approve, due 04 Nov 2026 (MSME cap) | 8.1, 9.5 |
| 02_happy_brighttech_scan | B modern | **Yes** | Approve, "PO 105" → PO-2026-105 | 1.2, 5.2, 8.2 |
| 03_edge_inferred_po_acme | C small biz | No | Approve, inferred PO-2026-104 | 5.7 |
| 04_edge_split_overbill_acme | C | No | Hold (PO ref is in the notes) | 6.5, 6.6 |
| 05_edge_duplicate_sahyadri_scan | A | **Yes** | Reject, duplicate of SEED-0003 | 7.2 (6.5 also fires; Reject wins) |
| 06_edge_bank_changed_brighttech | B | No | Hold (fraud), no vendor email | 4.7 |
| 07_extra_quotation_acme | C | No | Reject, not an invoice | 1.4 |
| 08_extra_wrong_split_brighttech | B | No | Hold, IGST expected | 8.3 |
| 09_extra_missing_date_deccan | A | No | Hold, vendor response loop | 3.2 |
| 10_extra_blocked_quickfix | C | No | Reject, blocked vendor | 4.5 (PO not found also fires) |

Tests should check that the listed codes are **present**, not that they're the only ones.

## Order effects to know about

Approvals consume PO balance, so order matters in a live session:

- Run **01** twice → the second is a duplicate (Reject). Good live demo of stage 7.
- If **06** is cleared by Finance and approved, PO-2026-116 is used up and **08** also shows over-balance. Reset before the video.
- Always **Reset demo data** before recording and before the interview.
