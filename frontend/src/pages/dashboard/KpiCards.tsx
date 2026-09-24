import type { ReactNode } from "react"

import { CodeChip } from "@/components/ds/StatusChip"
import { DECISION_TONE, DECISION_WORD } from "@/lib/decision"
import { cn } from "@/lib/utils"
import type { Decision, Stats } from "@/types"
import { duration, pct } from "./format"

function Card({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-3 rounded-card border border-line bg-raised p-6", className)}>
      <p className="label">{label}</p>
      {children}
    </div>
  )
}

function Big({ children }: { children: ReactNode }) {
  return <p className="num text-[44px] leading-none font-medium tracking-[-0.03em] text-ink">{children}</p>
}

function Sub({ children }: { children: ReactNode }) {
  return <p className="text-[14px] leading-relaxed text-ink-2">{children}</p>
}

export function KpiCards({ stats }: { stats: Stats }) {
  const k = stats.kpis
  const mp = k.money_protected
  const outcomes: { d: Decision; n: number }[] = [
    { d: "Approve", n: k.approved },
    { d: "Hold", n: k.held },
    { d: "Reject", n: k.rejected },
  ]
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 2xl:grid-cols-4">
      <Card label="Invoices processed">
        <Big>{k.processed}</Big>
        <Sub>{k.in_progress ? `${k.in_progress} more in progress right now.` : "Every check run, then decided."}</Sub>
      </Card>
      <Card label="Touchless rate">
        <Big>{pct(k.touchless_rate)}</Big>
        <Sub>{k.touchless} of {k.processed} approved without a person touching them.</Sub>
      </Card>
      <Card label="Time saved">
        <Big>{k.time_saved.hours.toLocaleString("en-IN")} h</Big>
        <Sub>
          Assumes {k.time_saved.minutes_per_invoice} minutes of manual AP work per invoice ({k.processed} ×{" "}
          {k.time_saved.minutes_per_invoice} min).
        </Sub>
      </Card>
      <Card label="Avg processing time">
        <Big>{duration(k.avg_processing_seconds)}</Big>
        <Sub>From upload to decision, including any time waiting for a person.</Sub>
      </Card>

      <Card label="Money protected" className="sm:col-span-2">
        <Big>{mp.display}</Big>
        <ul className="mt-1 flex flex-col">
          {mp.breakdown.map((b) => (
            <li key={b.key} className="flex items-baseline gap-3 border-t border-line py-2.5 text-[14px]">
              <span className="text-ink">{b.label}</span>
              <span className="font-mono text-[12px] text-ink-3">
                {b.runs} run{b.runs === 1 ? "" : "s"}
              </span>
              <span className="num ml-auto text-ink">{b.display}</span>
            </li>
          ))}
        </ul>
        <p className="text-[13px] leading-relaxed text-ink-3">
          Duplicates and fraud holds count the whole invoice; over-billing counts only the amount above the PO balance.
          Each run counts once.
        </p>
      </Card>

      <Card label="Outcomes" className="sm:col-span-2">
        <div className="grid grid-cols-3 gap-4">
          {outcomes.map(({ d, n }) => (
            <div key={d} className="flex flex-col gap-2">
              <Big>{n}</Big>
              <span className="flex items-center gap-2 text-[14px] text-ink-2">
                <span aria-hidden className="size-2.5 rounded-[3px]" style={{ background: DECISION_TONE[d].fg }} />
                {DECISION_WORD[d]}
              </span>
            </div>
          ))}
        </div>
        <ul className="mt-1 flex flex-col">
          <li className="flex items-baseline gap-3 border-t border-line py-2.5 text-[14px]">
            <span className="text-ink">Open in the review queue</span>
            <span className="num ml-auto text-ink">{k.open_review}</span>
          </li>
          <li className="flex items-baseline gap-3 border-t border-line py-2.5 text-[14px]">
            <span className="text-ink">Waiting on the vendor</span>
            <span className="num ml-auto text-ink">{k.waiting_on_vendor}</span>
          </li>
        </ul>
      </Card>
    </div>
  )
}

export function HealthStrip({ stats }: { stats: Stats }) {
  const h = stats.health
  const items: { label: string; value: string; note: ReactNode }[] = [
    {
      label: "Low-confidence reads",
      value: pct(h.low_confidence_share),
      note: <><CodeChip code="2.2" /> <span>{h.low_confidence_runs} run{h.low_confidence_runs === 1 ? "" : "s"}</span></>,
    },
    {
      label: "System errors",
      value: pct(h.system_error_share),
      note: <><CodeChip code="System error" /> <span>{h.system_error_runs} run{h.system_error_runs === 1 ? "" : "s"}</span></>,
    },
    {
      label: "LLM calls per run",
      value: h.llm_calls_per_run == null ? "—" : h.llm_calls_per_run.toFixed(1),
      note: <span>Cap is 2; cached files cost 0</span>,
    },
    {
      label: "Avg stage time",
      value: h.avg_stage_ms == null ? "—" : h.avg_stage_ms < 1000 ? `${h.avg_stage_ms} ms` : `${(h.avg_stage_ms / 1000).toFixed(1)} s`,
      note: <span>Per step, across every run</span>,
    },
  ]
  return (
    <dl className="grid grid-cols-1 gap-px overflow-hidden rounded-card border border-line bg-line sm:grid-cols-2 xl:grid-cols-4">
      {items.map((it) => (
        <div key={it.label} className="flex flex-col gap-2 bg-raised p-5">
          <dt className="label">{it.label}</dt>
          <dd className="num text-[28px] leading-none font-medium tracking-[-0.02em] text-ink">{it.value}</dd>
          <dd className="flex items-center gap-2 text-[13px] text-ink-3">{it.note}</dd>
        </div>
      ))}
    </dl>
  )
}
