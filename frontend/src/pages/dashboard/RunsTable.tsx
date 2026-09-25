import { useEffect, useState } from "react"
import { keepPreviousData, useQuery } from "@tanstack/react-query"

import { getRuns } from "@/api"
import { DataTable, type Column } from "@/components/ds/DataTable"
import { StatusChip } from "@/components/ds/StatusChip"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { DECISION_WORD } from "@/lib/decision"
import { when } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { Decision, RunSummary, Stats, StageStatus } from "@/types"

const ALL = "all"
const STATUSES = [
  { value: ALL, label: "Every status" },
  { value: "approved", label: "Approved" },
  { value: "needs_review", label: "In review queue" },
  { value: "waiting_on_vendor", label: "Waiting on vendor" },
  { value: "rejected", label: "Rejected" },
  { value: "superseded", label: "Superseded" },
  { value: "split", label: "Split" },
  { value: "running", label: "Running" },
]
const DECISION_CHIP: Record<Decision, StageStatus> = { Approve: "pass", Hold: "warn", Reject: "fail" }
const STATUS_NOTE: Record<string, string> = {
  needs_review: "In review queue",
  waiting_on_vendor: "Waiting on vendor",
  superseded: "Replaced by a corrected invoice",
  split: "Several invoices, each checked on its own",
}
const TRIGGER = "h-11! w-full rounded-full! border-line bg-raised pr-3 pl-4 text-[14px] text-ink hover:border-ink sm:w-52"

function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

export function RunsTable({ vendors, openId, onOpen }: { vendors: Stats["vendors"]; openId: string | null; onOpen: (id: string) => void }) {
  const [status, setStatus] = useState(ALL)
  const [vendor, setVendor] = useState(ALL)
  const [search, setSearch] = useState("")
  const q = useDebounced(search.trim())
  const filters = { status: status === ALL ? undefined : status, vendor: vendor === ALL ? undefined : vendor, q: q || undefined }
  const runs = useQuery({
    queryKey: ["runs", filters],
    queryFn: () => getRuns(filters),
    placeholderData: keepPreviousData,
    refetchInterval: 15_000,
  })
  const rows = runs.data ?? []
  const filtered = !!(filters.status || filters.vendor || filters.q)

  const columns: Column<RunSummary>[] = [
    {
      key: "run",
      head: "Invoice",
      cell: (r) => (
        <button type="button" onClick={(e) => { e.stopPropagation(); onOpen(r.run_id) }}
          className="flex flex-col items-start rounded-sm text-left">
          <span className="font-medium text-ink">{r.invoice_no ?? r.file_name ?? "Unreadable"}</span>
          <span className="font-mono text-[12px] text-ink-3">{r.run_id}</span>
        </button>
      ),
    },
    { key: "vendor", head: "Vendor", cell: (r) => <span className="text-ink-2">{r.vendor_name ?? "—"}</span> },
    { key: "total", head: "Total", align: "right", cell: (r) => r.total_display ?? "—" },
    {
      key: "decision",
      head: "Decision",
      cell: (r) => (
        <div className="flex flex-col items-start gap-1">
          {r.status === "running" ? <StatusChip status="info" word="Running" />
            : r.status === "superseded" ? <StatusChip status="info" word="Superseded" />
            : r.status === "split" ? <StatusChip status="info" word="Split" />
            : r.decision ? <StatusChip status={DECISION_CHIP[r.decision]} word={DECISION_WORD[r.decision]} /> : "—"}
          {STATUS_NOTE[r.status] && <span className="text-[12px] text-ink-3">{STATUS_NOTE[r.status]}</span>}
        </div>
      ),
    },
    {
      key: "reason",
      head: "Main reason",
      cell: (r) => <span className="line-clamp-2 max-w-md text-[13px] leading-snug text-ink-2">{r.top_reason ?? "—"}</span>,
    },
    { key: "when", head: "When", cell: (r) => <span className="num font-mono text-[12px] whitespace-nowrap text-ink-3">{when(r.created_at)}</span> },
  ]

  return (
    <div className="flex flex-col gap-5">
      <div role="search" className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger aria-label="Filter by status" className={TRIGGER}><SelectValue /></SelectTrigger>
          <SelectContent position="popper" sideOffset={6} className="rounded-input shadow-float">
            {STATUSES.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={vendor} onValueChange={setVendor}>
          <SelectTrigger aria-label="Filter by vendor" className={TRIGGER}><SelectValue /></SelectTrigger>
          <SelectContent position="popper" sideOffset={6} className="rounded-input shadow-float">
            <SelectItem value={ALL}>Every vendor</SelectItem>
            {vendors.map((v) => <SelectItem key={v.vendor_id} value={v.vendor_id}>{v.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search invoice no, run, PO, vendor, file"
          aria-label="Search runs"
          className="h-11 min-w-0 flex-1 rounded-input border border-line bg-raised px-4 text-[14px] text-ink placeholder:text-ink-3 hover:border-ink-3 sm:min-w-64"
        />
      </div>
      {runs.isError && <p role="alert" className="text-hold">Couldn't load the runs. Is the API running?</p>}
      {runs.isSuccess && !rows.length && (
        <p className="text-ink-2">{filtered ? "No runs match these filters." : "No runs yet."}</p>
      )}
      {rows.length > 0 && (
        <div className={cn("transition-opacity", runs.isPlaceholderData && "opacity-60")}>
          <DataTable caption="Runs" columns={columns} rows={rows} rowKey={(r) => r.run_id}
            onRowClick={(r) => onOpen(r.run_id)} rowClassName={(r) => cn(r.run_id === openId && "bg-hover")} />
        </div>
      )}
    </div>
  )
}
