const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

/** 0.3 → "30%". */
export function pct(share: number | null | undefined): string {
  return share == null ? "—" : `${Math.round(share * 100)}%`
}

/** Seconds → "4.2 s" / "3 min" / "2.5 h". */
export function duration(seconds: number | null | undefined): string {
  if (seconds == null) return "—"
  if (seconds < 60) return `${seconds.toFixed(1)} s`
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`
  return `${(seconds / 3600).toFixed(1)} h`
}

/** "2026-09-24" → "24 Sep" (a calendar day, no time zone shift). */
export function shortDay(isoDate: string): string {
  const [, m, d] = isoDate.split("-").map(Number)
  return `${d} ${MONTHS[m - 1]}`
}
