import { useState } from "react"
import { Link } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { getAlerts, sendAlert } from "@/api"
import { DataTable, type Column } from "@/components/ds/DataTable"
import { PillButton } from "@/components/ds/PillButton"
import { PillLink } from "@/components/ds/PillLink"
import { SectionTitle } from "@/components/ds/SectionTitle"
import { AlertStatusChip } from "@/components/ds/StatusChip"
import { SplitContainer } from "@/components/ds/SplitContainer"
import { when } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { AlertRow } from "@/types"

const FILTERS = ["All", "Drafted", "Sent", "Failed"] as const
type Filter = (typeof FILTERS)[number]

export function OutboxPage() {
  const [filter, setFilter] = useState<Filter>("All")
  const [openId, setOpenId] = useState<number | null>(null)
  const qc = useQueryClient()
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: getAlerts, refetchInterval: 15_000 })
  const send = useMutation({
    mutationFn: sendAlert,
    onSettled: (_d, _e, id) => {
      qc.invalidateQueries({ queryKey: ["alerts"] })
      const row = alerts.data?.find((a) => a.alert_id === id)
      if (row) qc.invalidateQueries({ queryKey: ["run", row.run_id] })
    },
  })

  const all = alerts.data ?? []
  const count = (f: Filter) => (f === "All" ? all.length : all.filter((a) => a.status === f).length)
  const rows = filter === "All" ? all : all.filter((a) => a.status === filter)
  const opened = all.find((a) => a.alert_id === openId) ?? null

  const columns: Column<AlertRow>[] = [
    { key: "audience", head: "Audience", cell: (a) => <span className="font-medium">{a.audience}</span> },
    { key: "for", head: "Intended for", cell: (a) => <span className="text-ink-2">{a.intended_for ?? "—"}</span> },
    { key: "subject", head: "Subject", cell: (a) => <span className="leading-snug">{a.subject}</span> },
    { key: "status", head: "Status", cell: (a) => <AlertStatusChip status={a.status} /> },
    { key: "sent", head: "Sent", cell: (a) => <span className="num font-mono text-[12px] text-ink-3">{a.sent_at ? when(a.sent_at) : "—"}</span> },
    {
      key: "run",
      head: "Run",
      cell: (a) => (
        <Link to={`/process?run=${encodeURIComponent(a.run_id)}`} className="font-mono text-[12px] text-accent underline-offset-2 hover:underline">
          {a.invoice_no ?? a.run_id}
        </Link>
      ),
    },
    {
      key: "actions",
      head: <span className="sr-only">Actions</span>,
      align: "right",
      cell: (a) => (
        <div className="flex items-center justify-end gap-3">
          <PillButton variant="link" arrow={false} aria-expanded={openId === a.alert_id}
            onClick={() => setOpenId((id) => (id === a.alert_id ? null : a.alert_id))}>
            {openId === a.alert_id ? "Hide" : "View"}
          </PillButton>
          {(a.status === "Drafted" || a.status === "Failed") && (
            <PillButton variant="secondary" className="h-9 px-4" disabled={send.isPending && send.variables === a.alert_id}
              onClick={() => send.mutate(a.alert_id)}>
              {send.isPending && send.variables === a.alert_id ? "Sending…" : a.status === "Failed" ? "Retry" : "Send"}
            </PillButton>
          )}
        </div>
      ),
    },
  ]

  const rail = (
    <>
      <h1 className="text-h1">Outbox</h1>
      <p className="text-[15px] leading-relaxed text-ink-2">
        Every email InvoiceIQ wrote. In this demo they all go to the owner's inbox; the person each one was meant for is
        printed at the top. Vendor emails wait here as drafts until someone presses Send, unless auto-send is on.
      </p>
      <nav aria-label="Filter emails" className="flex flex-col gap-2.5">
        <p className="label mb-1">Show</p>
        {FILTERS.map((f, i) => (
          <PillLink key={f} dot={i} active={filter === f} label={`${f} · ${count(f)}`} onClick={() => setFilter(f)} />
        ))}
      </nav>
    </>
  )

  return (
    <SplitContainer rail={rail}>
      <SectionTitle>{filter === "All" ? "Every email" : `${filter} emails`}</SectionTitle>
      {send.error && <p role="alert" className="mt-4 text-[14px] text-reject">{send.error.message}</p>}
      {alerts.isError && <p role="alert" className="mt-4 text-hold">Couldn't load the outbox. Is the API running?</p>}
      {alerts.isSuccess && !rows.length && (
        <p className="mt-4 text-ink-2">{all.length ? "No emails with this status." : "No emails yet. Process an invoice that needs attention and they'll appear here."}</p>
      )}
      {rows.length > 0 && (
        <div className="mt-6">
          <DataTable caption="Alerts" columns={columns} rows={rows} rowKey={(a) => String(a.alert_id)}
            rowClassName={(a) => cn(a.alert_id === openId && "bg-hover")} />
        </div>
      )}
      {opened && (
        <article aria-label="Email" className="mt-8 rounded-card border border-line bg-raised p-6">
          <header className="flex flex-wrap items-center gap-3">
            <AlertStatusChip status={opened.status} />
            <p className="font-medium text-ink">{opened.subject}</p>
          </header>
          <p className="mt-2 font-mono text-[12px] text-ink-3">
            To {opened.to_email} · intended for {opened.intended_for}
          </p>
          <pre className="mt-4 overflow-auto rounded-input border border-line bg-surface p-4 font-mono text-[13px] leading-relaxed whitespace-pre-wrap text-ink">
            {opened.body}
          </pre>
        </article>
      )}
    </SplitContainer>
  )
}
