import { useState, type ReactNode } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"

import { getVendorEmailPreview, previewVendorEmail } from "@/api"
import { inputCls } from "@/components/ds/Field"
import { PillButton } from "@/components/ds/PillButton"
import { CodeChip } from "@/components/ds/StatusChip"
import { clock, day } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { VendorEmailPreview, VendorReason } from "@/types"

const OTHER = "other"

/** The note drafted for the ticked reasons, in the same order and wording as the server drafts it. */
function draftFor(reasons: VendorReason[], ticked: string[]): string {
  const lines = reasons.filter((r) => ticked.includes(r.code)).flatMap((r) => r.suggestions)
  return [...new Set(lines)].join("\n")
}

const rowsFor = (text: string, min: number) => Math.max(min, text.split("\n").length + 1)

export type VendorEmail = { reasons: string[]; note: string; subject: string; body: string }

/** Send to vendor in two steps: pick reasons and edit the drafted note, then check and edit the email itself.
 * `alreadySent` is when an email already went to the vendor for this run; this one is then a follow-up. */
export function SendToVendor({ runId, busy, alreadySent = null, onSend }: {
  runId: string
  busy: boolean
  alreadySent?: string | null
  onSend: (email: VendorEmail) => void
}) {
  const draft = useQuery({ queryKey: ["vendor-email", runId], queryFn: () => getVendorEmailPreview(runId), staleTime: Infinity })
  if (draft.isLoading) return <p className="text-ink-3">Drafting the email…</p>
  if (draft.error) return <p role="alert" className="text-hold">{draft.error.message}</p>
  if (!draft.data) return null
  return (
    <div className="flex flex-col gap-4">
      {alreadySent && (
        <p className="rounded-input border border-line bg-surface px-4 py-3 text-[14px] text-ink">
          An email already went to the vendor at {clock(alreadySent)}
          {day(alreadySent) !== day(new Date().toISOString()) && ` on ${day(alreadySent)}`}. Sending again replaces its
          response link.
        </p>
      )}
      <Compose runId={runId} start={draft.data} busy={busy} followUp={!!alreadySent} onSend={onSend} />
    </div>
  )
}

function Compose({ runId, start, busy, followUp, onSend }: {
  runId: string
  start: VendorEmailPreview
  busy: boolean
  followUp: boolean
  onSend: (email: VendorEmail) => void
}) {
  const reasons = start.reasons
  const [ticked, setTicked] = useState<string[]>(start.selected)
  const [note, setNote] = useState(start.note)
  const [touched, setTouched] = useState(false) // once the note is edited, ticking chips no longer rewrites it
  const [email, setEmail] = useState<VendorEmailPreview | null>(null)
  const [subject, setSubject] = useState("")
  const [body, setBody] = useState("")

  const drafted = draftFor(reasons, ticked)
  const other = ticked.includes(OTHER)
  const needsNote = other && !note.trim()

  const toggle = (code: string) => {
    const next = ticked.includes(code) ? ticked.filter((c) => c !== code) : [...ticked, code]
    if (!next.length) return
    setTicked(next)
    if (!touched) setNote(draftFor(reasons, next))
  }

  const show = useMutation({
    mutationFn: () => previewVendorEmail(runId, { reasons: ticked, note }),
    onSuccess: (p) => {
      setEmail(p)
      setSubject(p.subject)
      setBody(p.body)
    },
  })

  if (email) {
    const edited = subject !== email.subject || body !== email.body
    const tooLong = subject.length > email.limits.subject || body.length > email.limits.body
    const ready = !!subject.trim() && !!body.trim() && !tooLong
    return (
      <form className="flex flex-col gap-4" onSubmit={(e) => {
        e.preventDefault()
        if (ready) onSend({ reasons: email.selected, note: email.note, subject, body })
      }}>
        <p className="font-mono text-[12px] leading-relaxed text-ink-3">
          For {email.intended_for}. Like every email here, it's delivered to the owner's inbox. The response link is
          created when you send it.
        </p>
        <label className="flex flex-col gap-1.5">
          <span className="label">Subject</span>
          <input value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={email.limits.subject + 50}
            className={cn(inputCls, "text-[14px]")} />
          <Limit n={subject.length} max={email.limits.subject} />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="label">Email</span>
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={rowsFor(body, 12) + 3}
            className={cn(inputCls, "h-auto py-3 font-mono text-[13px] leading-relaxed")} />
          <Limit n={body.length} max={email.limits.body} />
        </label>
        <Row>
          <PillButton type="submit" disabled={busy || !ready}>{followUp ? "Send follow-up" : "Send to vendor"}</PillButton>
          <PillButton type="button" variant="secondary" onClick={() => setEmail(null)} disabled={busy}>Back</PillButton>
          {edited && (
            <PillButton type="button" variant="link" arrow={false} disabled={busy}
              onClick={() => { setSubject(email.subject); setBody(email.body) }}>
              Undo my edits
            </PillButton>
          )}
        </Row>
      </form>
    )
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); if (!needsNote) show.mutate() }}>
      {show.error && <p role="alert" className="text-[14px] text-hold">{show.error.message}</p>}
      <div className="flex flex-col gap-2">
        <span className="label">What the vendor needs to fix</span>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Reasons">
          {reasons.map((r) => (
            <Chip key={r.code} on={ticked.includes(r.code)} last={ticked.length === 1} onClick={() => toggle(r.code)}
              title={r.messages.join(" ")}>
              <CodeChip code={r.code} tone={ticked.includes(r.code) ? "hold" : "neutral"} />
              {r.title}
            </Chip>
          ))}
          <Chip on={other} last={ticked.length === 1} onClick={() => toggle(OTHER)}>Other</Chip>
        </div>
        <p className="text-[13px] text-ink-3">Each ticked reason is listed in the email. At least one stays ticked.</p>
      </div>
      <label className="flex flex-col gap-1.5">
        <span className="label">Note to the vendor{other ? "" : " (optional)"}</span>
        <textarea value={note} rows={rowsFor(note, 2)}
          onChange={(e) => { setNote(e.target.value); setTouched(true) }}
          placeholder={other ? "Tell the vendor what to change." : "Anything to add for the vendor."}
          className={cn(inputCls, "h-auto py-3 leading-relaxed")} />
        <span className="flex flex-wrap items-baseline gap-x-3 text-[13px] text-ink-3">
          {drafted ? "Drafted from the findings; edit it as you like." : "Nothing to draft for these reasons; write your own."}
          {note !== drafted && drafted && (
            <button type="button" className="font-mono text-[12px] text-ink underline underline-offset-2 hover:text-accent"
              onClick={() => { setNote(drafted); setTouched(false) }}>
              Use the drafted note
            </button>
          )}
        </span>
      </label>
      <Row>
        <PillButton type="submit" disabled={busy || show.isPending || needsNote}>
          {show.isPending ? "Preparing…" : "Preview email"}
        </PillButton>
        {needsNote && <span className="text-[13px] text-ink-3">"Other" needs a note.</span>}
      </Row>
    </form>
  )
}

function Chip({ on, last, onClick, title, children }: {
  on: boolean
  last: boolean
  onClick: () => void
  title?: string
  children: ReactNode
}) {
  const locked = on && last
  return (
    <button type="button" role="checkbox" aria-checked={on} aria-disabled={locked || undefined} title={locked ? "At least one reason stays ticked" : title}
      onClick={() => { if (!locked) onClick() }}
      className={cn("inline-flex h-10 items-center gap-2 rounded-full border bg-raised pr-4 pl-2 text-[14px] transition-colors",
        on ? "border-ink text-ink" : "border-line text-ink-3 hover:border-ink-3",
        locked && "cursor-not-allowed")}>
      <span aria-hidden className={cn("grid size-4 place-items-center rounded-[3px] border text-[11px] leading-none",
        on ? "border-ink bg-ink text-white" : "border-ink-3")}>{on ? "✓" : ""}</span>
      {children}
    </button>
  )
}

const Row = ({ children }: { children: ReactNode }) => <div className="flex flex-wrap items-center gap-3">{children}</div>

const Limit = ({ n, max }: { n: number; max: number }) => (
  <span className={cn("text-right font-mono text-[12px]", n > max ? "text-reject" : "text-ink-3")}>
    {n.toLocaleString("en-IN")} / {max.toLocaleString("en-IN")}
  </span>
)
