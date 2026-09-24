import type { Extraction } from "@/types"

export type FieldKind = "text" | "money" | "date" | "days"
export type FieldDef = { key: keyof Extraction & string; label: string; kind: FieldKind; required?: boolean }

/** The fields a reviewer can correct, in reading order. Mirrors EDITABLE_FIELDS on the server. */
export const FIELDS: FieldDef[] = [
  { key: "vendor_name", label: "Vendor name", kind: "text" },
  { key: "vendor_gstin", label: "Vendor GSTIN", kind: "text" },
  { key: "invoice_number", label: "Invoice number", kind: "text", required: true },
  { key: "invoice_date", label: "Invoice date", kind: "date", required: true },
  { key: "po_reference", label: "PO reference", kind: "text" },
  { key: "subtotal", label: "Subtotal", kind: "money" },
  { key: "cgst", label: "CGST", kind: "money" },
  { key: "sgst", label: "SGST", kind: "money" },
  { key: "igst", label: "IGST", kind: "money" },
  { key: "total", label: "Total", kind: "money", required: true },
  { key: "bank_account", label: "Bank account", kind: "text" },
  { key: "ifsc", label: "IFSC", kind: "text" },
  { key: "payment_terms_days", label: "Payment terms (days)", kind: "days" },
]

export type Values = Record<string, string>

export function initialValues(ex: Extraction | null): Values {
  return Object.fromEntries(FIELDS.map((f) => [f.key, ex?.[f.key] == null ? "" : String(ex[f.key])]))
}

/** Only what the reviewer changed; blank is sent as null (the server never guesses a value). */
export function changedFields(start: Values, now: Values): Record<string, string | null> {
  const out: Record<string, string | null> = {}
  for (const f of FIELDS) {
    const a = (start[f.key] ?? "").trim()
    const b = (now[f.key] ?? "").trim()
    if (a !== b) out[f.key] = b === "" ? null : b
  }
  return out
}

/** Rupees as typed ("1,41,600.50") → paise, or null if it isn't a number. */
export function rupeesToPaise(v: string): number | null {
  const n = Number(v.replace(/[₹,\s]/g, ""))
  return v.trim() && Number.isFinite(n) ? Math.round(n * 100) : null
}
