import type { TaxType } from "@/types"

/** Python's round(): halves go to the even neighbour, so live totals match what the server stores. */
export function roundHalfEven(x: number): number {
  const r = Math.round(x)
  return Math.abs(x % 1) === 0.5 && r % 2 !== 0 ? r - 1 : r
}

/** "65,000.50" → 6500050 paise; null when it isn't a number. */
export function rupeesToPaise(text: string): number | null {
  const clean = text.replace(/[,₹\s]/g, "")
  if (!clean) return null
  const n = Number(clean)
  return Number.isFinite(n) ? roundHalfEven(n * 100) : null
}

export function toNumber(text: string): number | null {
  const clean = text.replace(/[,\s]/g, "")
  if (!clean) return null
  const n = Number(clean)
  return Number.isFinite(n) ? n : null
}

export type LineAmounts = { taxable: number; tax: number }

export function lineAmounts(qty: number | null, pricePaise: number | null, rate: number | null): LineAmounts | null {
  if (qty == null || pricePaise == null || qty <= 0 || pricePaise <= 0) return null
  const taxable = roundHalfEven(qty * pricePaise)
  return { taxable, tax: rate == null ? 0 : roundHalfEven((taxable * rate) / 100) }
}

/** Subtotal, tax split and total in paise, the way the server calculates them. */
export function poTotals(lines: (LineAmounts | null)[], split: TaxType | null) {
  const subtotal = lines.reduce((s, l) => s + (l?.taxable ?? 0), 0)
  const tax = split === "Import" ? 0 : lines.reduce((s, l) => s + (l?.tax ?? 0), 0)
  const cgst = split === "CGST+SGST" ? roundHalfEven(tax / 2) : 0
  return {
    subtotal,
    tax,
    cgst,
    sgst: split === "CGST+SGST" ? tax - cgst : 0,
    igst: split === "IGST" ? tax : 0,
    total: subtotal + tax,
  }
}

export function taxTypeFor(vendor: { country: string; state_code: string | null }, companyState: string | null): TaxType {
  if (vendor.country !== "IN") return "Import"
  return vendor.state_code === companyState ? "CGST+SGST" : "IGST"
}

export const TAX_TYPE_WORDS: Record<TaxType, string> = {
  "CGST+SGST": "CGST + SGST",
  IGST: "IGST",
  Import: "Import (no GST from the vendor)",
}
