/** GSTIN checks for inline validation; the server runs the same ones (backend/app/utils/gstin.py). */

const GSTIN_RE = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/
const CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

export const STATE_NAMES: Record<string, string> = {
  "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh", "05": "Uttarakhand",
  "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
  "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura", "17": "Meghalaya",
  "18": "Assam", "19": "West Bengal", "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh",
  "24": "Gujarat", "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra", "29": "Karnataka",
  "30": "Goa", "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
  "35": "Andaman and Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
}

export const normaliseGstin = (g: string) => g.toUpperCase().replace(/\s/g, "")

function checksum(first14: string): string {
  let total = 0
  for (let i = 0; i < 14; i++) {
    const product = CHARS.indexOf(first14[i]) * (i % 2 === 0 ? 1 : 2)
    total += Math.floor(product / 36) + (product % 36)
  }
  return CHARS[(36 - (total % 36)) % 36]
}

/** Why a GSTIN is wrong, or null when it passes. Same wording as the server. */
export function gstinProblem(raw: string): string | null {
  const g = normaliseGstin(raw)
  if (!g) return "Enter the vendor's GSTIN."
  if (g.length !== 15) return `A GSTIN has 15 characters; this one has ${g.length}.`
  if (!GSTIN_RE.test(g))
    return "That isn't a GSTIN: it should be a 2-digit state code, the 10-character PAN, an entity number, 'Z' and a check character (e.g. 36AABCA1234F1ZA)."
  if (!STATE_NAMES[g.slice(0, 2)]) return `The GSTIN starts with ${g.slice(0, 2)}, which isn't an Indian state code.`
  if (checksum(g.slice(0, 14)) !== g[14]) return "The check character doesn't match, so there's a typo somewhere in this GSTIN."
  return null
}

/** "29" → "Karnataka (29)". */
export function stateLabel(code: string | null | undefined): string | null {
  if (!code) return null
  return STATE_NAMES[code] ? `${STATE_NAMES[code]} (${code})` : `state ${code}`
}
