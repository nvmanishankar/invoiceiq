import { useState, type ReactNode } from "react"
import { useMutation } from "@tanstack/react-query"

import { reviewRun } from "@/api"
import { AccordionItem } from "@/components/ds/Accordion"
import { inputCls } from "@/components/ds/Field"
import { PillButton } from "@/components/ds/PillButton"
import { cn } from "@/lib/utils"
import { useRole } from "@/role"
import type { ReviewAction, RunDetail } from "@/types"

const SEND_BACK_REASONS = ["Unreadable scan", "Missing information", "Other"] as const
const PO_CODES = new Set(["5.3", "5.8", "5.9", "5.10"])
const FIELD_CODES = new Set(["2.2", "3.1", "3.2", "3.3", "sys"])

type Key = "confirm" | "pick_po" | "override" | "send_to_vendor" | "reject"

/** Which action fits the findings best; that one opens first. */
function suggested(run: RunDetail): Key | null {
  const holds = run.findings.filter((f) => f.severity === "hold")
  if (holds.some((f) => f.fraud)) return null
  if (holds.some((f) => FIELD_CODES.has(f.code))) return "confirm"
  if (holds.some((f) => PO_CODES.has(f.code))) return "pick_po"
  if (holds.some((f) => f.audience.includes("Vendor"))) return "send_to_vendor"
  return null
}

type Dict = Record<string, unknown>

/** PO candidates from stage 5's score table, best first. */
function candidates(run: RunDetail): { po_id: string; score: number | null }[] {
  const details = run.stages.find((s) => s.order === 5)?.details as Dict | undefined
  const scores = Array.isArray(details?.scores) ? (details.scores as Dict[]) : []
  return scores
    .filter((s) => typeof s.po_id === "string")
    .map((s) => ({ po_id: s.po_id as string, score: typeof s.total === "number" ? s.total : null }))
}

export function ReviewActions({
  run,
  changes,
  onDone,
}: {
  run: RunDetail
  changes: Record<string, string | null>
  onDone: (runId: string) => void
}) {
  const { role } = useRole()
  const fraud = run.findings.some((f) => f.fraud)
  const pick = suggested(run)
  const act = useMutation({
    mutationFn: (body: ReviewAction) => reviewRun(run.run_id, body, role),
    onSuccess: () => onDone(run.run_id),
  })
  const busy = act.isPending
  const nChanges = Object.keys(changes).length
  const hasPoStage = run.stages.some((s) => s.order === 5)

  return (
    <div className="flex flex-col gap-1">
      {act.error && (
        <div role="alert" className="mb-3 rounded-card border border-reject/30 bg-reject-bg p-4 text-[15px] text-ink">
          {act.error.message}
        </div>
      )}

      <Action title="Confirm and continue" note={nChanges ? `${nChanges} field(s) changed` : "Values as read"}
        open={pick === "confirm"} suggested={pick === "confirm"}>
        <p className="text-ink-2">
          Saves the fields above and runs the checks again from step 3. You'll watch it live on the Process page.
        </p>
        <Row>
          <PillButton disabled={busy} onClick={() => act.mutate({ action: "confirm", fields: changes })}>
            {nChanges ? "Save and continue" : "Confirm and continue"}
          </PillButton>
        </Row>
      </Action>

      {hasPoStage && (
        <Action title="Pick PO" note="Match to a PO you choose" open={pick === "pick_po"} suggested={pick === "pick_po"}>
          <PickPo run={run} busy={busy} onPick={(po_id) => act.mutate({ action: "pick_po", po_id })} />
        </Action>
      )}

      <Action title="Override and approve" note={fraud ? "Finance only on this invoice" : "Reason required"}>
        <ReasonForm
          label="Why approve anyway?"
          placeholder="e.g. Extra 100 reams agreed with Procurement by email on 17 Sep"
          busy={busy}
          blocked={fraud && role !== "Finance"
            ? "This invoice has a fraud finding. Only Finance can clear it, after calling the vendor on the number on file. Switch the role to Finance to continue."
            : null}
          button="Approve invoice"
          onSubmit={(reason) => act.mutate({ action: "override", reason })}
        />
      </Action>

      <Action title="Send to vendor" note={fraud ? "Not allowed on a fraud hold" : "Emails the vendor"}
        open={pick === "send_to_vendor"} suggested={pick === "send_to_vendor"}>
        {fraud ? (
          <Blocked>There's a fraud finding, so nothing goes to the vendor. Finance verifies it by phone instead.</Blocked>
        ) : (
          <SendBack busy={busy} onSend={(reason, note) => act.mutate({ action: "send_to_vendor", reason, note })} />
        )}
      </Action>

      <Action title="Reject" note="Closes the run">
        <ReasonForm
          label="Why reject?"
          placeholder="e.g. Vendor confirmed they never sent this invoice"
          busy={busy}
          button="Reject invoice"
          onSubmit={(reason) => act.mutate({ action: "reject", reason })}
        />
      </Action>
    </div>
  )
}

function Action({ title, note, open = false, suggested = false, children }: {
  title: string
  note: string
  open?: boolean
  suggested?: boolean
  children: ReactNode
}) {
  return (
    <AccordionItem
      defaultOpen={open}
      header={
        <span className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="font-medium text-ink">{title}</span>
          <span className="font-mono text-[12px] text-ink-3">{note}</span>
          {suggested && <span className="font-mono text-[11px] font-medium tracking-[0.06em] text-accent uppercase">Suggested</span>}
        </span>
      }
    >
      <div className="flex flex-col gap-4 pt-1">{children}</div>
    </AccordionItem>
  )
}

const Row = ({ children }: { children: ReactNode }) => <div className="flex flex-wrap items-center gap-3">{children}</div>

const Blocked = ({ children }: { children: ReactNode }) => (
  <p className="rounded-input border border-reject/30 bg-reject-bg px-4 py-3 text-[14px] leading-relaxed text-ink">{children}</p>
)

function ReasonForm({ label, placeholder, button, busy, blocked = null, onSubmit }: {
  label: string
  placeholder: string
  button: string
  busy: boolean
  blocked?: string | null
  onSubmit: (reason: string) => void
}) {
  const [reason, setReason] = useState("")
  if (blocked) return <Blocked>{blocked}</Blocked>
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault()
        if (reason.trim()) onSubmit(reason.trim())
      }}
    >
      <label className="flex flex-col gap-1.5">
        <span className="label">{label}</span>
        <textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder={placeholder} rows={2}
          className={cn(inputCls, "h-auto py-3 leading-relaxed")} />
      </label>
      <Row>
        <PillButton type="submit" disabled={busy || !reason.trim()}>{button}</PillButton>
      </Row>
    </form>
  )
}

function PickPo({ run, busy, onPick }: { run: RunDetail; busy: boolean; onPick: (poId: string) => void }) {
  const options = candidates(run)
  const [po, setPo] = useState(options[0]?.po_id ?? run.po_id ?? "")
  return (
    <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); if (po.trim()) onPick(po.trim()) }}>
      {options.length > 0 && (
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Candidate POs">
          {options.map((o) => (
            <button key={o.po_id} type="button" role="radio" aria-checked={po === o.po_id} onClick={() => setPo(o.po_id)}
              className={cn("inline-flex h-10 items-center gap-2 rounded-full border bg-raised px-4 font-mono text-[13px] text-ink transition-colors",
                po === o.po_id ? "border-ink" : "border-line hover:border-ink-3")}>
              {o.po_id}
              {o.score != null && <span className="num text-ink-3">{o.score.toFixed(1)}</span>}
            </button>
          ))}
        </div>
      )}
      <label className="flex flex-col gap-1.5">
        <span className="label">PO number</span>
        <input value={po} onChange={(e) => setPo(e.target.value)} placeholder="PO-2026-104"
          className={cn(inputCls, "max-w-xs font-mono text-[14px]")} />
      </label>
      <p className="text-[14px] text-ink-2">Amounts, duplicates, tax and dates are checked again against this PO (steps 6 to 9).</p>
      <Row>
        <PillButton type="submit" disabled={busy || !po.trim()}>Use this PO</PillButton>
      </Row>
    </form>
  )
}

function SendBack({ busy, onSend }: { busy: boolean; onSend: (reason: string, note?: string) => void }) {
  const [reason, setReason] = useState<string>("Missing information")
  const [note, setNote] = useState("")
  const needsNote = reason === "Other" && !note.trim()
  return (
    <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); if (!needsNote) onSend(reason, note.trim() || undefined) }}>
      <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Reason">
        {SEND_BACK_REASONS.map((r) => (
          <button key={r} type="button" role="radio" aria-checked={reason === r} onClick={() => setReason(r)}
            className={cn("h-10 rounded-full border bg-raised px-4 text-[14px] text-ink transition-colors",
              reason === r ? "border-ink" : "border-line hover:border-ink-3")}>
            {r}
          </button>
        ))}
      </div>
      <label className="flex flex-col gap-1.5">
        <span className="label">Note to the vendor{reason === "Other" ? "" : " (optional)"}</span>
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2}
          placeholder="e.g. Please reissue with 2,000 reams, the quantity on the PO."
          className={cn(inputCls, "h-auto py-3 leading-relaxed")} />
      </label>
      <p className="text-[14px] text-ink-2">The email lists every issue for the vendor, and the invoice waits for their reply.</p>
      <Row>
        <PillButton type="submit" disabled={busy || needsNote}>Send to vendor</PillButton>
      </Row>
    </form>
  )
}
