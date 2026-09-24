const inrFmt = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 })

/** Paise → "₹2,65,500" (paise shown only when non-zero). */
export function inr(paise: number | null | undefined): string {
  if (paise == null) return "—"
  const rupees = paise / 100
  return Number.isInteger(rupees) ? inrFmt.format(rupees).replace(/\.00$/, "") : inrFmt.format(rupees)
}

export function ms(n: number | null | undefined): string {
  if (n == null) return ""
  return n < 1000 ? `${Math.round(n)} ms` : `${(n / 1000).toFixed(1)} s`
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

/** ISO date → "04 Nov 2026". */
export function day(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso)
  if (Number.isNaN(d.getTime())) return iso
  return `${String(d.getDate()).padStart(2, "0")} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`
}

export function qty(n: number | null | undefined): string {
  return n == null ? "—" : new Intl.NumberFormat("en-IN").format(n)
}

/** How long since `iso`: "Waiting 3 days", "Waiting 5 hours", "Waiting under an hour". */
export function waitingFor(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "Waiting on the vendor"
  const hours = Math.floor((now - new Date(iso).getTime()) / 3_600_000)
  if (Number.isNaN(hours) || hours < 1) return "Waiting under an hour"
  if (hours < 24) return `Waiting ${hours} hour${hours === 1 ? "" : "s"}`
  const days = Math.floor(hours / 24)
  return `Waiting ${days} day${days === 1 ? "" : "s"}`
}

/** ISO timestamp → "14:32" in local time. */
export function clock(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
}

/** ISO timestamp → "24 Sep 14:32" in local time. */
export function when(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const hm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
  return `${String(d.getDate()).padStart(2, "0")} ${MONTHS[d.getMonth()]} ${hm}`
}
