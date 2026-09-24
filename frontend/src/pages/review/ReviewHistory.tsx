import { when } from "@/lib/format"
import type { FieldChange, ReviewEntry } from "@/types"

const ACTION: Record<string, string> = {
  confirm: "Confirmed and continued",
  pick_po: "Picked the PO",
  override: "Overrode and approved",
  send_to_vendor: "Sent back to the vendor",
  reject: "Rejected",
}

const shown = (display: string | null | undefined, raw: unknown) =>
  display ?? (raw == null || raw === "" ? "blank" : String(raw))

function change(key: string, c: FieldChange): string {
  return `${c.label ?? key} changed from ${shown(c.before_display, c.before)} to ${shown(c.after_display, c.after)}`
}

/** Every human action on this run: "Total changed from ₹1,18,000 to ₹1,81,000 by AP clerk, 24 Sep 14:32." */
export function ReviewHistory({ reviews }: { reviews: ReviewEntry[] }) {
  if (!reviews.length) return null
  return (
    <ol className="flex flex-col gap-3">
      {reviews.map((r) => {
        const by = `by ${r.reviewer ?? "someone"}, ${when(r.created_at)}`
        const changes = Object.entries(r.field_changes ?? {})
        return (
          <li key={r.review_id} className="rounded-card border border-line bg-raised px-5 py-4 text-[14px] leading-relaxed">
            <p className="text-ink">
              <span className="font-medium">{ACTION[r.action] ?? r.action}</span>{" "}
              <span className="text-ink-2">{by}</span>
            </p>
            {r.reason && <p className="mt-1 text-ink-2">Reason: {r.reason}</p>}
            {changes.length > 0 && (
              <ul className="mt-2 flex flex-col gap-1 font-mono text-[12px] text-ink-2">
                {changes.map(([k, c]) => <li key={k}>{change(k, c)}.</li>)}
              </ul>
            )}
          </li>
        )
      })}
    </ol>
  )
}
