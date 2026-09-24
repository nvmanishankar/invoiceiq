"""
InvoiceIQ seed kit generator.

Creates:
  backend/app/seed_data/*.json   company, vendors, tax rates, POs (+lines), ledger, goods receipts
  backend/samples/*.pdf          10 sample invoices (3 layouts, 2 simulated scans)
  backend/samples/expected.json  expected outcome per sample (used by tests + Tests page)

Run from repo root:  python backend/scripts/make_seed_and_samples.py
Requires: reportlab, pypdfium2, Pillow, numpy
All money in the JSON is integer paise (Rs 1 = 100 paise).
All email addresses are the owner's single inbox.
"""
import io
import json
import random
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageFilter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OWNER_EMAIL = "nvmanishankar@gmail.com"
ROOT = Path(__file__).resolve().parents[2]
SEED_DIR = ROOT / "backend" / "app" / "seed_data"
SAMPLE_DIR = ROOT / "backend" / "samples"
random.seed(7)

# --------------------------------------------------------------------------- GSTIN
CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_checksum(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        product = CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    return CHARS[(36 - total % 36) % 36]


def gstin(first14: str) -> str:
    return first14 + gstin_checksum(first14)


# --------------------------------------------------------------------------- money
def paise(rupees: float) -> int:
    return int(round(rupees * 100))


def inr(p: int) -> str:
    """Indian grouping, 2 decimals: 12345678 paise -> 1,23,456.78"""
    rupees, ps = divmod(abs(p), 100)
    s = str(rupees)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return f"{'-' if p < 0 else ''}{s}.{ps:02d}"


# --------------------------------------------------------------------------- master data
COMPANY = {
    "name": "Nimbus Retail Pvt Ltd",
    "address": "Plot 42, HITEC City, Madhapur, Hyderabad, Telangana 500081",
    "country": "IN",
    "gstin": gstin("36AAECN4321R1Z"),
    "state_code": "36",
    "currency": "INR",
    "tolerance_pct": 0.02,
    "tolerance_abs_paise": paise(5000),
    "ap_email": OWNER_EMAIL,
    "procurement_email": OWNER_EMAIL,
    "finance_email": OWNER_EMAIL,
    "vendor_auto_send": True,
}

VENDORS = [
    dict(vendor_id="V-01", name="Acme Supplies Private Limited", short="Acme Supplies",
         address="12-4-78, Nampally Station Road, Hyderabad, Telangana 500001",
         country="IN", currency="INR", tax_id=gstin("36AABCA1234F1Z"),
         bank_account="50100234564521", ifsc_or_swift="HDFC0001234", bank_name="HDFC Bank, Nampally",
         phone="+91 40 2461 7788", msme=False, status="Active"),
    dict(vendor_id="V-02", name="BrightTech Solutions Pvt Ltd", short="BrightTech Solutions",
         address="3rd Floor, Prestige Tech Park, Outer Ring Road, Bengaluru, Karnataka 560103",
         country="IN", currency="INR", tax_id=gstin("29AAFCB5678K1Z"),
         bank_account="91201004455667", ifsc_or_swift="UTIB0000123", bank_name="Axis Bank, Marathahalli",
         phone="+91 80 4112 9090", msme=False, status="Active"),
    dict(vendor_id="V-03", name="Zenith Logistics LLP", short="Zenith Logistics",
         address="A-17, Okhla Industrial Area Phase II, New Delhi 110020",
         country="IN", currency="INR", tax_id=gstin("07AAGCZ9012M1Z"),
         bank_account="30112233445566", ifsc_or_swift="SBIN0004567", bank_name="State Bank of India, Okhla",
         phone="+91 11 4055 2211", msme=False, status="Active"),
    dict(vendor_id="V-04", name="Deccan Office Interiors", short="Deccan Office Interiors",
         address="Plot 9, IDA Uppal, Hyderabad, Telangana 500039",
         country="IN", currency="INR", tax_id=gstin("36AAKFD3456Q1Z"),
         bank_account="61234567890123", ifsc_or_swift="ICIC0001122", bank_name="ICICI Bank, Uppal",
         phone="+91 40 2720 3344", msme=True, status="Active"),
    dict(vendor_id="V-05", name="Sahyadri Print House", short="Sahyadri Print House",
         address="Unit 14, Bhosari MIDC, Pune, Maharashtra 411026",
         country="IN", currency="INR", tax_id=gstin("27AAHCS7788L1Z"),
         bank_account="77889900112233", ifsc_or_swift="KKBK0000456", bank_name="Kotak Mahindra Bank, Bhosari",
         phone="+91 20 2712 6655", msme=False, status="Active"),
    dict(vendor_id="V-06", name="Quickfix Traders", short="Quickfix Traders",
         address="45 Anna Salai, Chennai, Tamil Nadu 600002",
         country="IN", currency="INR", tax_id=gstin("33AAQFQ1122B1Z"),
         bank_account="11223344556677", ifsc_or_swift="IOBA0000789", bank_name="Indian Overseas Bank, Anna Salai",
         phone="+91 44 2852 1100", msme=False, status="Blocked"),
]
for v in VENDORS:
    v["contact_email"] = OWNER_EMAIL
    v["created_by"] = "seed"
VENDOR = {v["vendor_id"]: v for v in VENDORS}

TAX_RATES = [
    dict(country="IN", tax_name="GST", rate=0, label="Nil / exempt", valid_from="2017-07-01", valid_to=None),
    dict(country="IN", tax_name="GST", rate=5, label="Merit", valid_from="2017-07-01", valid_to=None),
    dict(country="IN", tax_name="GST", rate=18, label="Standard", valid_from="2017-07-01", valid_to=None),
    dict(country="IN", tax_name="GST", rate=40, label="Demerit", valid_from="2025-09-22", valid_to=None),
    dict(country="IN", tax_name="GST", rate=3, label="Special: precious metals", valid_from="2017-07-01", valid_to=None),
    dict(country="IN", tax_name="GST", rate=12, label="Old slab", valid_from="2017-07-01", valid_to="2025-09-21"),
    dict(country="IN", tax_name="GST", rate=28, label="Old slab", valid_from="2017-07-01", valid_to="2025-09-21"),
]


def L(no, desc, hsn, qty, unit, price, rate=18):
    return dict(line_no=no, description=desc, hsn_code=hsn, qty=qty, unit=unit,
                unit_price_paise=paise(price), tax_rate=rate)


PURCHASE_ORDERS = [
    dict(po_id="PO-2026-101", vendor_id="V-01", po_date="2026-06-02", status="Open", payment_terms_days=30,
         department="Administration", lines=[L(1, "A4 copier paper 75gsm (ream of 500 sheets)", "4802", 2000, "ream", 200)]),
    dict(po_id="PO-2026-104", vendor_id="V-01", po_date="2026-08-20", status="Open", payment_terms_days=30,
         department="Facilities", lines=[L(1, "Ergonomic office chair, mesh back", "9401", 20, "pcs", 5000),
                                          L(2, "Chair floor mat", "3918", 20, "pcs", 1300)]),
    dict(po_id="PO-2026-117", vendor_id="V-01", po_date="2026-09-10", status="Open", payment_terms_days=30,
         department="Facilities", lines=[L(1, "Standard office chair", "9401", 25, "pcs", 4000)]),
    dict(po_id="PO-2026-105", vendor_id="V-02", po_date="2026-08-28", status="Open", payment_terms_days=30,
         department="IT", lines=[L(1, "Dell Latitude 5440 laptop, i5, 16GB RAM", "8471", 10, "pcs", 65000),
                                  L(2, "Laptop backpack 15.6 inch", "4202", 10, "pcs", 1200)]),
    dict(po_id="PO-2026-116", vendor_id="V-02", po_date="2026-09-15", status="Open", payment_terms_days=30,
         department="IT", lines=[L(1, "27 inch IPS monitor", "8528", 15, "pcs", 14000)]),
    dict(po_id="PO-2026-108", vendor_id="V-03", po_date="2026-09-05", status="Open", payment_terms_days=30,
         department="Operations", lines=[L(1, "Freight Hyderabad to Delhi, full truck load", "9965", 12, "trip", 25000)]),
    dict(po_id="PO-2026-109", vendor_id="V-04", po_date="2026-09-01", status="Open", payment_terms_days=60,
         department="Facilities", lines=[L(1, "Workstation desk 1400mm", "9403", 10, "pcs", 18000),
                                          L(2, "Pedestal drawer unit", "9403", 10, "pcs", 4500)]),
    dict(po_id="PO-2026-110", vendor_id="V-04", po_date="2026-09-05", status="Open", payment_terms_days=30,
         department="Facilities", lines=[L(1, "Conference table, 8-seater", "9403", 2, "pcs", 35000)]),
    dict(po_id="PO-2026-112", vendor_id="V-05", po_date="2026-07-10", status="Closed", payment_terms_days=30,
         department="Marketing", lines=[L(1, "Tri-fold brochures", "4911", 10000, "pcs", 8)]),
    dict(po_id="PO-2026-114", vendor_id="V-05", po_date="2026-08-25", status="Open", payment_terms_days=30,
         department="Marketing", lines=[L(1, "Printed brochures A4", "4911", 5000, "pcs", 12)]),
]
for po in PURCHASE_ORDERS:
    po["currency"] = "INR"
    po["created_by"] = "seed"

GOODS_RECEIPTS = [
    dict(po_id="PO-2026-101", line_no=1, qty_received=2000, received_date="2026-08-10"),
    dict(po_id="PO-2026-104", line_no=1, qty_received=20, received_date="2026-09-12"),
    dict(po_id="PO-2026-104", line_no=2, qty_received=20, received_date="2026-09-12"),
    dict(po_id="PO-2026-105", line_no=1, qty_received=10, received_date="2026-09-18"),
    dict(po_id="PO-2026-105", line_no=2, qty_received=10, received_date="2026-09-18"),
    dict(po_id="PO-2026-109", line_no=1, qty_received=10, received_date="2026-09-17"),
    dict(po_id="PO-2026-109", line_no=2, qty_received=10, received_date="2026-09-17"),
    dict(po_id="PO-2026-110", line_no=1, qty_received=2, received_date="2026-09-19"),
    dict(po_id="PO-2026-114", line_no=1, qty_received=5000, received_date="2026-09-03"),
    dict(po_id="PO-2026-116", line_no=1, qty_received=15, received_date="2026-09-19"),
]


# --------------------------------------------------------------------------- invoice maths
def build_totals(lines, split):
    """split: 'intra' -> CGST+SGST halves, 'inter' -> IGST."""
    sub = sum(int(l["qty"] * l["unit_price_paise"]) for l in lines)
    tax = sum(int(round(l["qty"] * l["unit_price_paise"] * l["tax_rate"] / 100)) for l in lines)
    if split == "intra":
        return dict(subtotal=sub, cgst=tax // 2, sgst=tax - tax // 2, igst=0, total=sub + tax)
    return dict(subtotal=sub, cgst=0, sgst=0, igst=tax, total=sub + tax)


# Already-approved invoices (history before the app went live)
LEDGER = []


def ledger_row(run_id, invoice_no, vendor_id, po_id, date, lines, split):
    t = build_totals(lines, split)
    LEDGER.append(dict(run_id=run_id, invoice_no=invoice_no, vendor_id=vendor_id,
                       vendor_tax_id=VENDOR[vendor_id]["tax_id"], po_id=po_id, invoice_date=date,
                       po_match_type="Explicit", decision="Approve", status="approved", is_seed=True,
                       bank_account=VENDOR[vendor_id]["bank_account"],
                       subtotal_paise=t["subtotal"], cgst_paise=t["cgst"], sgst_paise=t["sgst"],
                       igst_paise=t["igst"], total_paise=t["total"],
                       lines=[dict(line_no=l["line_no"], description=l["description"], qty=l["qty"],
                                   unit=l["unit"], unit_price_paise=l["unit_price_paise"],
                                   tax_rate=l["tax_rate"], matched_po_line=l["line_no"]) for l in lines]))


ledger_row("SEED-0001", "ACME/2026/0311", "V-01", "PO-2026-101", "2026-07-10",
           [L(1, "A4 copier paper 75gsm (ream of 500 sheets)", "4802", 800, "ream", 200)], "intra")
ledger_row("SEED-0002", "ACME/2026/0388", "V-01", "PO-2026-101", "2026-08-12",
           [L(1, "A4 copier paper 75gsm (ream of 500 sheets)", "4802", 700, "ream", 200)], "intra")
ledger_row("SEED-0003", "SPH/INV-0042", "V-05", "PO-2026-114", "2026-09-05",
           [L(1, "Printed brochures A4", "4911", 5000, "pcs", 12)], "inter")


# --------------------------------------------------------------------------- sample definitions
def sample(file, layout, vendor_id, invoice_no, date, po_ref, lines, split, *, title="TAX INVOICE",
           scan=False, bank=None, ifsc=None, terms=None, po_in_notes=False, expected=None, story=None):
    return dict(file=file, layout=layout, vendor_id=vendor_id, invoice_no=invoice_no, date=date,
                po_ref=po_ref, lines=lines, split=split, title=title, scan=scan, bank=bank, ifsc=ifsc,
                terms=terms, po_in_notes=po_in_notes, expected=expected, story=story)


SAMPLES = [
    sample("01_happy_deccan.pdf", "A", "V-04", "DOI/2026-27/0158", "2026-09-20", "PO-2026-109",
           [L(1, "Workstation desk 1400mm", "9403", 10, "pcs", 18000),
            L(2, "Pedestal drawer unit", "9403", 10, "pcs", 4500)], "intra", terms="Payment within 60 days",
           story="Clean text PDF, explicit PO, same state (CGST+SGST). MSME vendor with 60-day PO terms.",
           expected=dict(decision="Approve", codes=["8.1", "9.5"], po_id="PO-2026-109", match_type="Explicit",
                         due_date="2026-11-04",
                         note="Due date capped at 45 days because Deccan is MSME (PO says 60).")),
    sample("02_happy_brighttech_scan.pdf", "B", "V-02", "BT/26/0874", "2026-09-22", "PO 105",
           [L(1, "Dell Latitude 5440 laptop, i5, 16GB RAM", "8471", 10, "pcs", 65000),
            L(2, "Laptop backpack 15.6 inch", "4202", 10, "pcs", 1200)], "inter", scan=True,
           story="Scanned image PDF, PO written as 'PO 105', other state (IGST).",
           expected=dict(decision="Approve", codes=["1.2", "5.2", "8.2"], po_id="PO-2026-105",
                         match_type="Explicit", due_date="2026-10-22")),
    sample("03_edge_inferred_po_acme.pdf", "C", "V-01", "ACME/2026/0402", "2026-09-15", None,
           [L(1, "ErgoPro Mesh Ergonomic Chair", "9401", 20, "pcs", 5000)], "intra",
           story="No PO reference anywhere. Three Acme POs survive the filters; line-item scoring picks "
                 "PO-2026-104 over PO-2026-117 (which matches the amount exactly) and PO-2026-101.",
           expected=dict(decision="Approve", codes=["5.7"], po_id="PO-2026-104", match_type="Inferred",
                         confidence="High", due_date="2026-10-15",
                         note="Scores ~82.6 (PO-104) vs ~48.3 (PO-117) vs ~30.0 (PO-101).")),
    sample("04_edge_split_overbill_acme.pdf", "C", "V-01", "ACME/2026/0417", "2026-09-18", "PO-2026-101",
           [L(1, "A4 copier paper 75gsm (ream of 500 sheets)", "4802", 600, "ream", 200)], "intra",
           po_in_notes=True,
           story="Third invoice on PO-2026-101. PO total 4,72,000; 3,54,000 already approved; 1,18,000 left. "
                 "This invoice is 1,41,600 and takes quantity to 2,100 of 2,000. PO reference is in the notes.",
           expected=dict(decision="Hold", codes=["6.5", "6.6"], po_id="PO-2026-101", match_type="Explicit",
                         alerts=["Vendor"])),
    sample("05_edge_duplicate_sahyadri_scan.pdf", "A", "V-05", "42", "2026-09-05", "PO-2026-114",
           [L(1, "Printed brochures A4", "4911", 5000, "pcs", 12)], "inter", scan=True,
           story="Re-scanned copy of SPH/INV-0042 (already approved), resubmitted with the number written as '42'.",
           expected=dict(decision="Reject", codes=["7.2"], po_id="PO-2026-114", duplicate_of="SEED-0003",
                         alerts=["Vendor", "AP"])),
    sample("06_edge_bank_changed_brighttech.pdf", "B", "V-02", "BT/26/0917", "2026-09-20", "PO-2026-116",
           [L(1, "27 inch IPS monitor", "8528", 15, "pcs", 14000)], "inter",
           bank="50200099887766", ifsc="HDFC0009876",
           story="Everything matches PO-2026-116 except the bank account (ends 7766; master ends 5667).",
           expected=dict(decision="Hold", codes=["4.7"], po_id="PO-2026-116", fraud=True,
                         alerts=["Finance", "AP"], no_vendor_email=True)),
    sample("07_extra_quotation_acme.pdf", "C", "V-01", "QT/ACME/2026/077", "2026-09-22", None,
           [L(1, "Ergonomic office chair, mesh back", "9401", 10, "pcs", 5200),
            L(2, "Chair floor mat", "3918", 10, "pcs", 1350)], "intra", title="QUOTATION",
           story="A quotation sent to the AP inbox instead of an invoice.",
           expected=dict(decision="Reject", codes=["1.4"], alerts=["Vendor"])),
    sample("08_extra_wrong_split_brighttech.pdf", "B", "V-02", "BT/26/0931", "2026-09-21", "PO-2026-116",
           [L(1, "27 inch IPS monitor", "8528", 5, "pcs", 14000)], "intra",
           story="Karnataka vendor billing a Telangana buyer with CGST+SGST instead of IGST. Totals are right.",
           expected=dict(decision="Hold", codes=["8.3"], po_id="PO-2026-116", alerts=["Vendor"])),
    sample("09_extra_missing_date_deccan.pdf", "A", "V-04", "DOI/2026-27/0171", None, "PO-2026-110",
           [L(1, "Conference table, 8-seater", "9403", 2, "pcs", 35000)], "intra",
           story="No invoice date. Use it to demo the vendor response link loop.",
           expected=dict(decision="Hold", codes=["3.2"], po_id="PO-2026-110", alerts=["Vendor"])),
    sample("10_extra_blocked_quickfix.pdf", "C", "V-06", "QFT/0093", "2026-09-19", "PO-2026-099",
           [L(1, "Toner cartridge, compatible", "8443", 20, "pcs", 2500)], "inter",
           story="Invoice from a blocked vendor quoting a PO that doesn't exist.",
           expected=dict(decision="Reject", codes=["4.5"], alerts=["Procurement"])),
]


# --------------------------------------------------------------------------- PDF layouts
W, H = A4


def fmt_date(iso):
    if not iso:
        return ""
    y, m, d = iso.split("-")
    months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    return f"{int(d):02d} {months[int(m) - 1]} {y}"


def words_total(p):
    return f"INR {inr(p)} only"


def draw_items_table(c, x, y, lines, cols, font, size=8.5, zebra=None, grid=True, header_fill=None,
                     header_color=colors.black):
    """cols: list of (title, width, key, align). Returns y after table."""
    row_h = 18
    total_w = sum(cw for _, cw, _, _ in cols)
    if header_fill:
        c.setFillColor(header_fill)
        c.rect(x, y - row_h, total_w, row_h, stroke=0, fill=1)
    c.setFillColor(header_color)
    c.setFont(font + "-Bold" if font != "Times-Roman" else "Times-Bold", size)
    cx = x
    for title, cw, _, align in cols:
        tx = cx + cw - 4 if align == "R" else cx + 4
        (c.drawRightString if align == "R" else c.drawString)(tx, y - 12, title)
        cx += cw
    c.setFillColor(colors.black)
    y -= row_h
    c.setFont(font, size)
    for i, ln in enumerate(lines):
        if zebra and i % 2 == 0:
            c.setFillColor(zebra)
            c.rect(x, y - row_h, total_w, row_h, stroke=0, fill=1)
            c.setFillColor(colors.black)
        cx = x
        for _, cw, key, align in cols:
            val = key(i, ln)
            tx = cx + cw - 4 if align == "R" else cx + 4
            (c.drawRightString if align == "R" else c.drawString)(tx, y - 12, str(val))
            cx += cw
        if grid:
            c.setStrokeColor(colors.HexColor("#999999"))
            c.line(x, y - row_h, x + total_w, y - row_h)
        y -= row_h
    if grid:
        c.setStrokeColor(colors.HexColor("#999999"))
        c.rect(x, y, total_w, row_h * (len(lines) + 1), stroke=1, fill=0)
        cx = x
        for _, cw, _, _ in cols[:-1]:
            cx += cw
            c.line(cx, y, cx, y + row_h * (len(lines) + 1))
    c.setStrokeColor(colors.black)
    return y


def std_cols():
    return [
        ("#", 22, lambda i, l: i + 1, "L"),
        ("Description", 196, lambda i, l: l["description"], "L"),
        ("HSN/SAC", 52, lambda i, l: l["hsn_code"], "L"),
        ("Qty", 44, lambda i, l: f"{l['qty']:g}", "R"),
        ("Unit", 36, lambda i, l: l["unit"], "L"),
        ("Rate (Rs.)", 70, lambda i, l: inr(l["unit_price_paise"]), "R"),
        ("GST %", 38, lambda i, l: f"{l['tax_rate']:g}", "R"),
        ("Amount (Rs.)", 77, lambda i, l: inr(int(l["qty"] * l["unit_price_paise"])), "R"),
    ]


def totals_block(c, x, y, t, split, font, rate_note, size=9):
    rows = [("Taxable value", t["subtotal"])]
    if split == "intra":
        rows += [(f"CGST @ {rate_note / 2:g}%", t["cgst"]), (f"SGST @ {rate_note / 2:g}%", t["sgst"])]
    else:
        rows += [(f"IGST @ {rate_note:g}%", t["igst"])]
    bold = font + "-Bold" if font != "Times-Roman" else "Times-Bold"
    for label, val in rows:
        c.setFont(font, size)
        c.drawString(x, y, label)
        c.drawRightString(x + 170, y, inr(val))
        y -= 14
    c.line(x, y + 9, x + 170, y + 9)
    c.setFont(bold, size + 1.5)
    c.drawString(x, y - 4, "Total (Rs.)")
    c.drawRightString(x + 170, y - 4, inr(t["total"]))
    return y - 22


def layout_A(c, s, v, t):
    """Formal table invoice (Helvetica, full grid)."""
    f = "Helvetica"
    c.setFont(f + "-Bold", 15)
    c.drawString(40, H - 55, v["name"])
    c.setFont(f, 8.5)
    c.drawString(40, H - 70, v["address"])
    c.drawString(40, H - 82, f"GSTIN: {v['tax_id']}    Phone: {v['phone']}")
    c.setFont(f + "-Bold", 16)
    c.drawRightString(W - 40, H - 55, s["title"])
    c.setFont(f, 8)
    c.drawRightString(W - 40, H - 68, "Original for recipient")
    c.line(40, H - 95, W - 40, H - 95)

    # meta box
    meta = [("Invoice No.", s["invoice_no"]), ("Invoice Date", fmt_date(s["date"])),
            ("PO Reference", s["po_ref"] or ""), ("Place of supply", "Telangana (36)")]
    y = H - 115
    for k, val in meta:
        c.setFont(f + "-Bold", 9)
        c.drawString(330, y, k)
        c.setFont(f, 9)
        c.drawString(420, y, val)
        y -= 14
    c.setFont(f + "-Bold", 9)
    c.drawString(40, H - 115, "Bill to")
    c.setFont(f, 9)
    c.drawString(40, H - 129, COMPANY["name"])
    c.drawString(40, H - 141, "Plot 42, HITEC City, Madhapur")
    c.drawString(40, H - 153, "Hyderabad, Telangana 500081")
    c.drawString(40, H - 165, f"GSTIN: {COMPANY['gstin']}")

    y = draw_items_table(c, 40, H - 190, s["lines"], std_cols(), f)
    y = totals_block(c, W - 240, y - 20, t, s["split"], f, s["lines"][0]["tax_rate"])
    c.setFont(f, 8.5)
    c.drawString(40, y, f"Amount in words: {words_total(t['total'])}")
    y -= 30
    c.setFont(f + "-Bold", 9)
    c.drawString(40, y, "Bank details")
    c.setFont(f, 9)
    c.drawString(40, y - 13, f"Account name: {v['name']}")
    c.drawString(40, y - 25, f"A/c No: {s['bank'] or v['bank_account']}   IFSC: {s['ifsc'] or v['ifsc_or_swift']}")
    c.drawString(40, y - 37, v["bank_name"] if not s["bank"] else "HDFC Bank, Secunderabad")
    if s["terms"]:
        c.drawString(40, y - 55, f"Terms: {s['terms']}")
    c.drawRightString(W - 40, y - 37, f"For {v['name']}")
    c.drawRightString(W - 40, y - 70, "Authorised Signatory")
    c.setFont(f, 7)
    c.drawString(40, 40, "We declare that this invoice shows the actual price of the goods described and that all "
                         "particulars are true and correct.")


def layout_B(c, s, v, t):
    """Modern invoice: dark band header, zebra rows."""
    f = "Helvetica"
    band = colors.HexColor("#1F3A5F")
    c.setFillColor(band)
    c.rect(0, H - 110, W, 110, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont(f + "-Bold", 20)
    c.drawString(40, H - 55, v["short"].upper())
    c.setFont(f, 9)
    c.drawString(40, H - 72, v["address"])
    c.drawString(40, H - 85, f"GSTIN {v['tax_id']}  |  {v['phone']}")
    c.setFont(f + "-Bold", 26)
    c.drawRightString(W - 40, H - 60, "INVOICE" if s["title"] == "TAX INVOICE" else s["title"])
    c.setFillColor(colors.black)

    c.setFont(f, 8)
    c.setFillColor(colors.HexColor("#666666"))
    c.drawString(40, H - 135, "BILLED TO")
    c.drawString(300, H - 135, "INVOICE DETAILS")
    c.setFillColor(colors.black)
    c.setFont(f + "-Bold", 10)
    c.drawString(40, H - 150, COMPANY["name"])
    c.setFont(f, 9)
    c.drawString(40, H - 163, "Plot 42, HITEC City, Madhapur, Hyderabad 500081")
    c.drawString(40, H - 175, f"GSTIN {COMPANY['gstin']}")
    y = H - 150
    for k, val in [("Invoice #", s["invoice_no"]), ("Date", fmt_date(s["date"])),
                   ("Your order", s["po_ref"] or "-"), ("Due", "30 days from invoice date")]:
        c.setFont(f, 9)
        c.drawString(300, y, k)
        c.setFont(f + "-Bold", 9)
        c.drawString(380, y, val)
        y -= 13

    cols = [
        ("ITEM", 230, lambda i, l: l["description"], "L"),
        ("HSN", 50, lambda i, l: l["hsn_code"], "L"),
        ("QTY", 45, lambda i, l: f"{l['qty']:g}", "R"),
        ("UNIT PRICE", 80, lambda i, l: inr(l["unit_price_paise"]), "R"),
        ("TAX", 35, lambda i, l: f"{l['tax_rate']:g}%", "R"),
        ("AMOUNT", 75, lambda i, l: inr(int(l["qty"] * l["unit_price_paise"])), "R"),
    ]
    y = draw_items_table(c, 40, H - 215, s["lines"], cols, f, zebra=colors.HexColor("#EEF2F7"), grid=False,
                         header_fill=band, header_color=colors.white)
    y = totals_block(c, W - 240, y - 25, t, s["split"], f, s["lines"][0]["tax_rate"])
    c.setStrokeColor(colors.HexColor("#1F3A5F"))
    c.roundRect(40, y - 70, 250, 70, 6, stroke=1, fill=0)
    c.setFont(f + "-Bold", 9)
    c.drawString(50, y - 15, "PAY TO")
    c.setFont(f, 9)
    c.drawString(50, y - 29, v["name"])
    c.drawString(50, y - 42, f"Account {s['bank'] or v['bank_account']}")
    c.drawString(50, y - 55, f"IFSC {s['ifsc'] or v['ifsc_or_swift']}")
    if s["bank"]:
        c.setFont(f + "-Oblique", 8)
        c.drawString(40, y - 85, "Please note: our bank details have been updated. Kindly use the account above.")
    c.setFont(f, 8)
    c.setFillColor(colors.HexColor("#666666"))
    c.drawString(40, 40, f"Thank you for your business. Queries: accounts@{v['short'].split()[0].lower()}.example")
    c.setFillColor(colors.black)


def layout_C(c, s, v, t):
    """Small-business invoice: Times, centred header, notes section."""
    f = "Times-Roman"
    c.setFont("Times-Bold", 17)
    c.drawCentredString(W / 2, H - 55, v["name"].upper())
    c.setFont(f, 9.5)
    c.drawCentredString(W / 2, H - 70, v["address"])
    c.drawCentredString(W / 2, H - 82, f"GSTIN: {v['tax_id']}  *  Ph: {v['phone']}")
    c.line(60, H - 92, W - 60, H - 92)
    c.setFont("Times-Bold", 14)
    c.drawCentredString(W / 2, H - 112, s["title"])
    c.setFont(f, 10)
    c.drawString(60, H - 140, f"No: {s['invoice_no']}")
    c.drawRightString(W - 60, H - 140, f"Date: {fmt_date(s['date'])}")
    c.drawString(60, H - 160, f"To: {COMPANY['name']}, Hyderabad (GSTIN {COMPANY['gstin']})")
    if s["po_ref"] and not s["po_in_notes"]:
        c.drawString(60, H - 175, f"Order ref: {s['po_ref']}")
    y = draw_items_table(c, 40, H - 195, s["lines"], std_cols(), f, size=9)
    if s["title"] == "QUOTATION":
        c.setFont(f, 10)
        c.drawString(60, y - 25, f"Estimated taxable value: Rs. {inr(t['subtotal'])} plus GST as applicable.")
        c.drawString(60, y - 40, "This quotation is valid for 30 days. Prices subject to change thereafter.")
        c.drawString(60, y - 55, "Please send your purchase order to confirm.")
        y -= 75
    else:
        y = totals_block(c, W - 240, y - 25, t, s["split"], f, s["lines"][0]["tax_rate"], size=10)
    c.setFont("Times-Bold", 10)
    c.drawString(60, y - 5, "Notes")
    c.setFont(f, 10)
    notes = []
    if s["po_in_notes"]:
        notes.append(f"Supplied against your purchase order {s['po_ref']} (third part-delivery).")
    notes.append("Goods once sold will not be taken back. Subject to Hyderabad jurisdiction.")
    for i, n in enumerate(notes):
        c.drawString(60, y - 20 - i * 14, n)
    y = y - 30 - len(notes) * 14
    if s["title"] != "QUOTATION":
        c.drawString(60, y - 10, f"Bank: {v['bank_name']}  A/c {s['bank'] or v['bank_account']}  "
                                 f"IFSC {s['ifsc'] or v['ifsc_or_swift']}")
    c.drawRightString(W - 60, 90, f"for {v['name']}")
    c.drawRightString(W - 60, 60, "Proprietor / Authorised Signatory")


LAYOUTS = {"A": layout_A, "B": layout_B, "C": layout_C}


def render_pdf(s) -> bytes:
    v = VENDOR[s["vendor_id"]]
    t = build_totals(s["lines"], s["split"])
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"{s['title']} {s['invoice_no']}")
    c.setAuthor(v["name"])
    LAYOUTS[s["layout"]](c, s, v, t)
    c.showPage()
    c.save()
    return buf.getvalue()


def to_scan(pdf_bytes: bytes) -> bytes:
    """Render to image, rotate slightly, add noise and blur, save as image-only PDF (no text layer)."""
    page = pdfium.PdfDocument(pdf_bytes)[0]
    img = page.render(scale=150 / 72).to_pil().convert("L")
    img = img.rotate(random.uniform(-1.6, 1.6), resample=Image.BICUBIC, expand=True, fillcolor=255)
    arr = np.asarray(img).astype(np.int16)
    arr = arr + np.random.default_rng(3).normal(0, 9, arr.shape).astype(np.int16)
    arr = np.clip(arr * 0.93 + 12, 0, 255).astype(np.uint8)          # slightly washed out
    img = Image.fromarray(arr).filter(ImageFilter.GaussianBlur(0.6))
    out = io.BytesIO()
    img.convert("RGB").save(out, format="PDF", resolution=150)
    return out.getvalue()


# --------------------------------------------------------------------------- write everything
def main():
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    dump = lambda name, obj: (SEED_DIR / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False))
    dump("company.json", COMPANY)
    dump("vendors.json", VENDORS)
    dump("tax_rates.json", TAX_RATES)
    dump("purchase_orders.json", PURCHASE_ORDERS)
    dump("ledger.json", LEDGER)
    dump("goods_receipts.json", GOODS_RECEIPTS)

    expected = []
    for s in SAMPLES:
        data = render_pdf(s)
        if s["scan"]:
            data = to_scan(data)
        (SAMPLE_DIR / s["file"]).write_bytes(data)
        t = build_totals(s["lines"], s["split"])
        expected.append(dict(file=s["file"], story=s["story"], vendor_id=s["vendor_id"],
                             invoice_no=s["invoice_no"], invoice_date=s["date"], po_ref_printed=s["po_ref"],
                             total_paise=t["total"], scanned=s["scan"], **s["expected"]))
    (SAMPLE_DIR / "expected.json").write_text(json.dumps(expected, indent=2, ensure_ascii=False))
    print(f"Wrote seed data to {SEED_DIR} and {len(SAMPLES)} samples to {SAMPLE_DIR}")


if __name__ == "__main__":
    main()
