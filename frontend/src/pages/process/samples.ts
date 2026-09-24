/** Friendly names for the demo samples, keyed by the number prefix of the file. */
const NAMES: Record<string, string> = {
  "01": "Happy path",
  "02": "Scanned, 'PO 105'",
  "03": "No PO reference",
  "04": "Over-billed PO",
  "05": "Duplicate scan",
  "06": "Bank changed",
  "07": "A quotation",
  "08": "Wrong tax split",
  "09": "Missing date",
  "10": "Blocked vendor",
}

export function sampleName(file: string): string {
  return NAMES[file.slice(0, 2)] ?? file.replace(/\.pdf$/i, "").replace(/_/g, " ")
}
