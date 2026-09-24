import { useState } from "react"
import { useSearchParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"

import { getPos } from "@/api"
import { ProcurementOnly } from "@/components/ProcurementOnly"
import { PillButton } from "@/components/ds/PillButton"
import { PillLink } from "@/components/ds/PillLink"
import { SectionTitle } from "@/components/ds/SectionTitle"
import { SplitContainer } from "@/components/ds/SplitContainer"
import { inr } from "@/lib/format"
import type { PoRow } from "@/types"
import { PoForm } from "./PoForm"
import { PoTable } from "./PoTable"

const FILTERS = ["All", "Open", "Closed"] as const
type Filter = (typeof FILTERS)[number]

/** ?create opens the form (?create=V-07 picks the vendor); ?po=… opens that PO's row. */
export function PosPage() {
  const [params, setParams] = useSearchParams()
  const creating = params.has("create")
  const [filter, setFilter] = useState<Filter>("All")
  const [openIds, setOpenIds] = useState<Set<string>>(() => new Set(params.get("po") ? [params.get("po")!] : []))
  const [created, setCreated] = useState<PoRow | null>(null)
  const pos = useQuery({ queryKey: ["pos"], queryFn: getPos })

  const all = pos.data ?? []
  const rows = filter === "All" ? all : all.filter((p) => p.status === filter)
  const count = (f: Filter) => (f === "All" ? all.length : all.filter((p) => p.status === f).length)
  const openBalance = all.filter((p) => p.status === "Open").reduce((s, p) => s + Math.max(p.remaining_paise, 0), 0)

  const toggle = (id: string) =>
    setOpenIds((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const rail = (
    <>
      <h1 className="text-h1">Purchase orders</h1>
      <p className="text-[15px] leading-relaxed text-ink-2">
        What the company agreed to buy. Every invoice is checked against these, and only approved invoices use up a
        PO's balance.
        {pos.isSuccess && <> Open POs have <span className="num text-ink">{inr(openBalance)}</span> left to bill.</>}
      </p>
      <ProcurementOnly action="raise purchase orders">
        {(disabled) => (
          <PillButton disabled={disabled || creating} onClick={() => { setCreated(null); setParams({ create: "" }) }}>
            Create PO
          </PillButton>
        )}
      </ProcurementOnly>
      <nav aria-label="Filter purchase orders" className="flex flex-col gap-2.5">
        <p className="label mb-1">Show</p>
        {FILTERS.map((f, i) => (
          <PillLink key={f} dot={i + 1} active={!creating && filter === f} label={`${f} · ${count(f)}`}
            onClick={() => { setFilter(f); if (creating) setParams({}) }} />
        ))}
      </nav>
    </>
  )

  return (
    <SplitContainer rail={rail}>
      {creating ? (
        <PoForm
          key={params.get("create") ?? ""}
          initialVendor={params.get("create") || null}
          onCancel={() => setParams({})}
          onCreated={(po) => {
            setCreated(po)
            setFilter("All")
            setOpenIds(new Set([po.po_id]))
            setParams({ po: po.po_id })
          }}
        />
      ) : (
        <>
          <SectionTitle>{filter === "All" ? "Every PO" : `${filter} POs`}</SectionTitle>
          {created && (
            <div role="status" className="mt-6 rounded-card border border-approve/30 bg-approve-bg px-5 py-4 text-[15px] text-ink">
              <span className="font-mono font-medium">{created.po_id}</span> created for {created.vendor_name}:{" "}
              <span className="num">{created.total_display}</span>. Invoices quoting it will now match.
              {created.warnings?.map((w) => <p key={w} className="mt-1.5 text-[14px] text-hold">{w}</p>)}
            </div>
          )}
          {pos.isError && <p role="alert" className="mt-4 text-hold">Couldn't load the POs. Is the API running?</p>}
          {pos.isSuccess && !rows.length && <p className="mt-4 text-ink-2">No POs with this status.</p>}
          {rows.length > 0 && (
            <div className="mt-6">
              <PoTable rows={rows} openIds={openIds} onToggle={toggle} />
            </div>
          )}
        </>
      )}
    </SplitContainer>
  )
}
