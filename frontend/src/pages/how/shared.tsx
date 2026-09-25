import type { ReactNode } from "react"
import { Link } from "react-router-dom"

import { PillButton } from "@/components/ds/PillButton"
import { SectionTitle } from "@/components/ds/SectionTitle"
import { CodeChip, StatusChip } from "@/components/ds/StatusChip"
import { cn } from "@/lib/utils"
import type { Audience, CaseOutcome, CatalogueCase } from "@/types"
import { AUDIENCE_LABEL, OUTCOME_STATUS, OUTCOME_TONE } from "./labels"

/** One page section: anchor, bar title, a mono kicker and a one-line lede. */
export function Section({ id, title, kicker, lede, children }: {
  id: string
  title: ReactNode
  kicker: string
  lede?: ReactNode
  children: ReactNode
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-24 border-t border-line pt-12 first:border-t-0 first:pt-0">
      <p className="label mb-3">{kicker}</p>
      <SectionTitle id={`${id}-title`}>{title}</SectionTitle>
      {lede && <p className="mt-4 max-w-2xl text-[16px] leading-relaxed text-ink-2">{lede}</p>}
      <div className="mt-8">{children}</div>
    </section>
  )
}

export function OutcomeChip({ outcome, also }: { outcome: CaseOutcome; also?: CaseOutcome | null }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <StatusChip status={OUTCOME_STATUS[outcome]} word={outcome} />
      {also && (
        <>
          <span className="font-mono text-[11px] text-ink-3">or</span>
          <StatusChip status={OUTCOME_STATUS[also]} word={also} />
        </>
      )}
    </span>
  )
}

export function CaseCodeChip({ c }: { c: Pick<CatalogueCase, "code" | "outcome"> }) {
  return <CodeChip code={c.code} tone={OUTCOME_TONE[c.outcome]} />
}

export function Alerted({ who, fraud }: { who: Audience[]; fraud?: boolean }) {
  return (
    <span className="text-[13px] text-ink-2">
      {who.length ? who.map((a) => AUDIENCE_LABEL[a]).join(", ") : "No one"}
      {fraud && <span className="text-reject"> · never the vendor</span>}
    </span>
  )
}

export function BuiltBadge({ status }: { status: CatalogueCase["status"] }) {
  const built = status === "Built"
  return (
    <span className={cn(
      "inline-flex h-6 items-center rounded-full border px-2.5 font-mono text-[11px] tracking-[0.04em]",
      built ? "border-line bg-raised text-ink" : "border-dashed border-ink-3 text-ink-3",
    )}>
      {built ? "Built" : "Designed, not built yet"}
    </span>
  )
}

export function AiBadge({ ai }: { ai: boolean }) {
  return (
    <span className={cn(
      "inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 font-mono text-[11px] font-medium tracking-[0.06em] uppercase",
      ai ? "bg-accent text-white" : "bg-ink text-white",
    )}>
      <span aria-hidden className="size-1.5 rounded-[1px] bg-current" />
      {ai ? "AI" : "Rule"}
    </span>
  )
}

export function TryIt({ sample }: { sample: string }) {
  return (
    <PillButton asChild variant="link" className="text-[12px]">
      <Link to={`/process?sample=${encodeURIComponent(sample)}`} aria-label={`Try it: run sample ${sample} on the Process page`}>
        Try it
      </Link>
    </PillButton>
  )
}

/** Small segmented control: a row of pills, one pressed. */
export function Segmented<T extends string>({ options, value, onChange, label }: {
  options: { value: T; label: ReactNode }[]
  value: T
  onChange: (v: T) => void
  label: string
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex flex-wrap gap-1 rounded-full border border-line bg-raised p-1">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "h-8 rounded-full px-3.5 font-mono text-[12px] transition-colors duration-200",
            value === o.value ? "bg-ink text-white" : "text-ink-2 hover:bg-hover hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("rounded-card border border-line bg-raised p-5", className)}>{children}</div>
}
