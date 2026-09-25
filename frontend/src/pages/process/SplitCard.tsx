import { Link } from "react-router-dom"

import { PillButton } from "@/components/ds/PillButton"
import { StatusChip } from "@/components/ds/StatusChip"
import { DECISION_WORD } from "@/lib/decision"
import type { Decision, SplitChild, StageStatus } from "@/types"

const DECISION_CHIP: Record<Decision, StageStatus> = { Approve: "pass", Hold: "warn", Reject: "fail" }
const STATUS_NOTE: Record<string, string> = {
  needs_review: "In review queue",
  waiting_on_vendor: "Waiting on vendor",
  superseded: "Replaced by a corrected invoice",
}

const pagesText = (pages: number[]) =>
  pages.length > 1 ? `Pages ${pages[0]}–${pages[pages.length - 1]}` : pages.length ? `Page ${pages[0]}` : null

/** Case 1.6: the invoices found in one PDF, each checked as its own run. Statuses update as they finish. */
export function SplitCard({ items }: { items: SplitChild[] }) {
  return (
    <section aria-labelledby="split-title" className="rounded-card border border-line bg-raised">
      <div className="px-6 pt-6 pb-4 md:px-7">
        <h2 id="split-title" className="text-[20px] leading-snug font-medium tracking-[-0.02em] text-ink">
          This PDF had {items.length} invoices, so each is checked on its own
        </h2>
        <p className="mt-1.5 text-[14px] leading-relaxed text-ink-2">
          One after another, in page order. Each gets its own decision.
        </p>
      </div>
      <ul className="border-t border-line">
        {items.map((c) => (
          <li key={c.run_id} className="flex flex-wrap items-center gap-x-5 gap-y-3 border-b border-line px-6 py-4 last:border-b-0 md:px-7">
            <div className="min-w-0 flex-1 basis-56">
              <p className="truncate font-medium text-ink">{c.invoice_no ?? "No invoice number"}</p>
              <p className="truncate text-[13px] text-ink-2">
                {c.vendor_name ?? "Unknown vendor"}
                <span className="font-mono text-ink-3"> · {[pagesText(c.pages), c.run_id].filter(Boolean).join(" · ")}</span>
              </p>
            </div>
            <p className="num font-mono text-[14px] text-ink">{c.total_display ?? "—"}</p>
            <div className="flex w-40 flex-col items-start gap-1">
              {c.status === "running" || !c.decision ? (
                <StatusChip status="info" word="Checking…" />
              ) : (
                <StatusChip status={DECISION_CHIP[c.decision]} word={DECISION_WORD[c.decision]} />
              )}
              {STATUS_NOTE[c.status] && <span className="text-[12px] text-ink-3">{STATUS_NOTE[c.status]}</span>}
            </div>
            <PillButton asChild variant="secondary" className="h-9 px-4">
              <Link to={`/process?run=${encodeURIComponent(c.run_id)}`} aria-label={`Open ${c.invoice_no ?? c.run_id}`}>
                Open
              </Link>
            </PillButton>
          </li>
        ))}
      </ul>
    </section>
  )
}
