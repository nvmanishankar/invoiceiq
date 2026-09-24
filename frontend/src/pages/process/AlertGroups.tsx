import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"

import { sendAlert } from "@/api"
import { PillButton } from "@/components/ds/PillButton"
import { SectionTitle } from "@/components/ds/SectionTitle"
import { AlertStatusChip, CodeChip } from "@/components/ds/StatusChip"
import { cn } from "@/lib/utils"
import type { AlertRow, RunDetail } from "@/types"

const ORDER = ["Finance", "AP", "Procurement", "Vendor"]
const TONE = { pass: "pass", hold: "hold", reject: "reject", info: "info" } as const

/** Who would be told, and what. One card per audience, with the email's status once it's built. */
export function AlertGroups({ run }: { run: RunDetail }) {
  const groups = run.alert_groups
  const audiences = Object.keys(groups.by_audience).sort((a, b) => ORDER.indexOf(a) - ORDER.indexOf(b))
  const suppressed = groups.vendor_suppressed && !audiences.includes("Vendor")
  // The newest email per audience: a reviewer's send-back replaces the first vendor email.
  const alertFor = (aud: string) => run.alerts.filter((a) => a.audience === aud).at(-1)
  return (
    <section aria-labelledby="alerts-title">
      <SectionTitle id="alerts-title">Who gets told</SectionTitle>
      {!audiences.length && !suppressed && (
        <p className="mt-4 text-ink-2">Nobody needs to act. The invoice goes straight to payment.</p>
      )}
      <div className="mt-6 grid gap-3 empty:hidden md:grid-cols-2">
        {audiences.map((aud) => {
          const alert = alertFor(aud)
          return (
            <article key={aud} className="flex flex-col rounded-card border border-line bg-raised p-5">
              <header className="flex items-center justify-between gap-3">
                <h3 className="text-h3">{aud}</h3>
                {alert && <AlertStatusChip status={alert.status} />}
              </header>
              {alert && <p className="mt-1 font-mono text-[12px] text-ink-3">For {alert.intended_for}</p>}
              <ul className="mt-3 flex flex-col gap-2">
                {groups.by_audience[aud].map((f, i) => (
                  <li key={`${f.code}-${i}`} className="flex gap-2.5 text-[14px] leading-relaxed text-ink">
                    <CodeChip code={f.label ?? f.code} tone={TONE[f.severity as keyof typeof TONE] ?? "neutral"} />
                    <span>{f.message}</span>
                  </li>
                ))}
              </ul>
              {alert && <EmailFooter alert={alert} runId={run.run_id} />}
            </article>
          )
        })}
        {suppressed && (
          <article className={cn("rounded-card border border-dashed border-reject/50 bg-reject-bg/50 p-5")}>
            <h3 className="text-h3">Vendor</h3>
            <p className="mt-2 font-mono text-[13px] font-medium text-reject">Vendor email suppressed</p>
            <p className="mt-1 text-[14px] leading-relaxed text-ink-2">
              There's a fraud finding on this invoice, so nothing goes to the vendor. Finance calls them on the number on file.
            </p>
          </article>
        )}
      </div>
    </section>
  )
}

/** Subject, the full email on demand, and Send for a draft (Retry for a failure). */
export function EmailFooter({ alert, runId }: { alert: AlertRow; runId: string }) {
  const [open, setOpen] = useState(false)
  const qc = useQueryClient()
  const send = useMutation({
    mutationFn: () => sendAlert(alert.alert_id),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["run", runId] })
      qc.invalidateQueries({ queryKey: ["alerts"] })
    },
  })
  const canSend = alert.status === "Drafted" || alert.status === "Failed"
  return (
    <div className="mt-4 border-t border-line pt-3">
      <p className="text-[13px] leading-snug text-ink-2">{alert.subject}</p>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <PillButton variant="link" arrow={false} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {open ? "Hide email" : "View email"}
        </PillButton>
        {canSend && (
          <PillButton variant="secondary" className="ml-auto h-9 px-4" onClick={() => send.mutate()} disabled={send.isPending}>
            {send.isPending ? "Sending…" : alert.status === "Failed" ? "Retry" : "Send"}
          </PillButton>
        )}
      </div>
      {send.error && <p role="alert" className="mt-2 text-[13px] text-reject">{send.error.message}</p>}
      {open && (
        <pre className="mt-3 max-h-80 overflow-auto rounded-input border border-line bg-surface p-4 font-mono text-[12px] leading-relaxed whitespace-pre-wrap text-ink">
          {alert.body}
        </pre>
      )}
    </div>
  )
}
