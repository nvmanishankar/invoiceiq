import { SectionTitle } from "@/components/ds/SectionTitle"
import { inr } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { PoView } from "@/types"

/** How much of the PO was left for this invoice, and what's left after it. */
export function PoBalance({ po, invoicePaise, approved }: { po: PoView; invoicePaise: number | null; approved: boolean }) {
  const total = Math.max(po.total_paise, 1)
  const billed = (po.invoiced_before_paise / total) * 100
  const thisInv = invoicePaise ?? 0
  const over = thisInv > po.remaining_before_paise
  const thisPct = Math.min((thisInv / total) * 100, 100 - billed)
  return (
    <section aria-labelledby="po-title">
      <SectionTitle id="po-title">{po.po_id} balance</SectionTitle>
      <div className="mt-6 rounded-card border border-line bg-raised p-6 md:p-7">
        <dl className="grid grid-cols-2 gap-5 md:grid-cols-4">
          <Stat k="PO total" v={po.total_display} />
          <Stat k="Left before this invoice" v={po.remaining_before_display} />
          <Stat k="This invoice" v={inr(invoicePaise)} tone={over ? "text-hold" : undefined} />
          <Stat k={approved ? "Left after this invoice" : "Still left (not billed while held)"} v={po.remaining_display} />
        </dl>
        <div className="mt-6 flex h-2.5 overflow-hidden rounded-full bg-hover" role="img"
          aria-label={`${po.invoiced_before_display} billed before, ${inr(invoicePaise)} on this invoice, ${po.total_display} total`}>
          <div className="bg-ink" style={{ width: `${billed}%` }} />
          <div className={cn(over ? "dither-strip text-hold" : approved ? "bg-accent" : "bg-accent/40")} style={{ width: `${Math.max(thisPct, 0)}%` }} />
        </div>
        <div className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-ink-2">
          <Legend cls="bg-ink" label={`Billed before: ${po.invoiced_before_display}`} />
          <Legend cls={over ? "bg-hold" : "bg-accent"} label={over ? "This invoice: more than what's left" : "This invoice"} />
        </div>
      </div>
    </section>
  )
}

function Stat({ k, v, tone }: { k: string; v: string; tone?: string }) {
  return (
    <div>
      <dt className="text-[13px] text-ink-3">{k}</dt>
      <dd className={cn("num mt-1 text-[20px] font-medium tracking-[-0.01em] text-ink", tone)}>{v}</dd>
    </div>
  )
}

function Legend({ cls, label }: { cls: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span aria-hidden className={cn("size-2 rounded-[1px]", cls)} />
      {label}
    </span>
  )
}
