import { useState } from "react"

import { FraudBanner } from "@/components/ds/FraudBanner"
import { CodeChip } from "@/components/ds/StatusChip"
import { cn } from "@/lib/utils"
import type { Audience, Catalogue, VendorLoop } from "@/types"
import { AUDIENCE_LABEL } from "./labels"
import { Section } from "./shared"
import { SHOTS } from "./shots"
import { Shot } from "./Shot"

const WHO: { a: Audience; gets: string; subject: (loop: VendorLoop | undefined) => string; extra: string }[] = [
  {
    a: "Vendor",
    gets: "What they must fix on their invoice: each problem the checks found, as a plain sentence, plus a note from AP when a reviewer sends it.",
    subject: (l) => l?.email.subject ?? "[InvoiceIQ → Vendor: …] Invoice … needs a correction · Ref RUN-…",
    extra: "A Hold carries the upload link. A Reject says not to resend. Sent at once if vendor auto-send is on; otherwise it waits in the Outbox.",
  },
  {
    a: "AP",
    gets: "Judgement calls for the AP team: files that can't be read, fields read with low confidence, possible duplicates, credit notes, two POs that both fit, old or overdue invoices, and system errors.",
    subject: () => "[InvoiceIQ → AP] On hold: invoice … from …",
    extra: "Also copied on every fraud hold, and told when a vendor uploads a correction through their link. A held invoice's email links straight to it in Review.",
  },
  {
    a: "Procurement",
    gets: "Problems on our side: an unknown or blocked vendor, a closed PO, an invoice dated before its PO, or no PO that fits.",
    subject: () => "[InvoiceIQ → Procurement] On hold: invoice … from …",
    extra: "A held invoice's email links straight to it in Review.",
  },
  {
    a: "Finance",
    gets: "Fraud only: a GSTIN that isn't the one on file, or a bank account that changed.",
    subject: () => "[InvoiceIQ → Finance · Fraud check] Verify … before paying invoice …",
    extra: "Tells Finance to call the vendor on the phone number in the vendor master and to clear or reject the hold.",
  },
]

export function AlertsSection({ catalogue, loop, onCase }: {
  catalogue: Catalogue | undefined
  loop: VendorLoop | undefined
  onCase: (code: string) => void
}) {
  const [open, setOpen] = useState<Audience>("Vendor")
  const cases = (a: Audience) => (catalogue?.cases ?? []).filter((c) => c.status === "Built" && c.alerted.includes(a))
  const who = WHO.find((w) => w.a === open)!

  return (
    <Section
      id="alerts"
      kicker="12 · Alerts"
      title="Who gets which email"
      lede="When the checks finish, each audience gets one email listing every issue for them, filled from templates with the findings' own sentences. An approval with nothing to flag emails no one."
    >
      <FraudBanner title="The fraud rule">
        On a fraud finding (4.6, 4.7) the vendor is never emailed: no email is written for them, the Outbox refuses to
        send one, and their upload link closes. Finance is told to call the number already in the vendor master and not to
        reply to the email that brought the invoice. InvoiceIQ never emails an address taken from an invoice at all: it
        doesn't read one.
      </FraudBanner>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4" role="tablist" aria-label="Audience">
        {WHO.map((w) => {
          const on = open === w.a
          return (
            <button key={w.a} type="button" role="tab" aria-selected={on} aria-controls="alerts-panel" onClick={() => setOpen(w.a)}
              className={cn(
                "flex flex-col items-start gap-1 rounded-card border p-5 text-left transition-colors duration-200",
                on ? "border-ink bg-raised" : "border-line bg-raised hover:border-ink-3",
                w.a === "Finance" && on && "border-reject",
              )}>
              <span className="text-[17px] font-medium text-ink">{AUDIENCE_LABEL[w.a]}</span>
              <span className="font-mono text-[12px] text-ink-3">{catalogue ? `${cases(w.a).length} cases` : "…"}</span>
            </button>
          )
        })}
      </div>

      <div id="alerts-panel" role="tabpanel" aria-live="polite" className="mt-3 grid gap-4 rounded-card border border-line bg-raised p-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-3">
          <p className="text-[15px] leading-relaxed text-ink">{who.gets}</p>
          <p className="text-[14px] leading-relaxed text-ink-2">{who.extra}</p>
          <div className="rounded-[14px] bg-bubble px-4 py-3">
            <p className="label">Subject</p>
            <p className="mt-1 font-mono text-[13px] leading-relaxed break-words text-ink">{who.subject(loop)}</p>
          </div>
        </div>
        <div>
          <p className="label mb-2">Cases that email {AUDIENCE_LABEL[open]}</p>
          <ul className="flex flex-wrap gap-x-3 gap-y-2">
            {cases(open).map((c) => (
              <li key={c.code}>
                <button type="button" onClick={() => onCase(c.code)} aria-label={`Show case ${c.code}, ${c.title}, in the 9 checks`}
                  className="group inline-flex items-center gap-1.5 rounded-full">
                  <CodeChip code={c.code} tone={c.fraud ? "reject" : "neutral"} />
                  <span className="text-[13px] text-ink-2 group-hover:text-ink">{c.title}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <p className="mt-4 text-[14px] leading-relaxed text-ink-2">
        In this demo every email goes to the owner's inbox, with the intended recipient on its first line, and replies
        come back there too. The Outbox lists each one as Sent, Drafted or Failed.
      </p>

      <div className="mt-8">
        <Shot {...SHOTS.process}
          alt="The Process page for sample 06: the nine steps, the Hold decision with a fraud banner, and alerts for Finance and AP only"
          caption="Sample 06 on the Process page: the bank account changed, so it's held as fraud. Finance and AP are told; the vendor is not." />
      </div>
    </Section>
  )
}
