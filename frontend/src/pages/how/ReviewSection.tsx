import { useState, type ReactNode } from "react"
import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"

import { getPoWalkthrough } from "@/api"
import { AccordionItem } from "@/components/ds/Accordion"
import { Field, inputCls } from "@/components/ds/Field"
import { PillButton } from "@/components/ds/PillButton"
import { CodeChip } from "@/components/ds/StatusChip"
import { cn } from "@/lib/utils"
import type { Catalogue, HowFacts, Permission, VendorLoop } from "@/types"
import { Alerted, Card, Section, Segmented } from "./shared"
import { SHOTS } from "./shots"
import { Shot } from "./Shot"

type Key = "confirm" | "pick_po" | "override" | "send_to_vendor" | "reject"
type Kind = "hold" | "fraud"

const ACTIONS: { key: Key; title: string; note: string; fraudNote?: string }[] = [
  { key: "confirm", title: "Confirm and continue", note: "Values as read" },
  { key: "pick_po", title: "Pick PO", note: "Match to a PO you choose" },
  { key: "override", title: "Override and approve", note: "Reason required", fraudNote: "Finance only on this invoice" },
  { key: "send_to_vendor", title: "Send to vendor", note: "Emails the vendor", fraudNote: "Not allowed on a fraud hold" },
  { key: "reject", title: "Reject", note: "Closes the run" },
]

export function ReviewSection({ catalogue, facts, loop, onCase }: {
  catalogue: Catalogue | undefined
  facts: HowFacts | undefined
  loop: VendorLoop | undefined
  onCase: (code: string) => void
}) {
  const [key, setKey] = useState<Key>("confirm")
  const [kind, setKind] = useState<Kind>("hold")
  const perm = facts?.permissions.find((p) => p.key === key)
  const action = ACTIONS.find((a) => a.key === key)!

  return (
    <Section
      id="review"
      kicker="08 · Review"
      title="When an invoice goes to review"
      lede="A Hold means a person has to look. The invoice waits in the Review queue, oldest first, with every finding and its evidence. Five actions settle it."
    >
      <HoldSituations catalogue={catalogue} onCase={onCase} />

      <h3 className="mt-12 text-h3">The five review actions</h3>
      <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ink-2">
        Pick an action to see what it does and who may do it. Every action is written to the invoice's history with
        the role, the time and what changed.
      </p>
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <Segmented label="Review action" value={key} onChange={setKey}
          options={ACTIONS.map((a) => ({ value: a.key, label: a.title }))} />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Card className="flex flex-col gap-5">
          <div>
            <p className="label">What happens</p>
            <p className="mt-1.5 text-[15px] leading-relaxed text-ink">{whatHappens(key, facts)}</p>
          </div>
          <div>
            <p className="label">Who may do it</p>
            {perm ? <Who perm={perm} /> : <p className="mt-1.5 text-ink-3">Loading…</p>}
          </div>
        </Card>

        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="label">Replica · the real review controls, switched off</p>
            {action.fraudNote && (
              <Segmented label="Kind of hold" value={kind} onChange={setKind}
                options={[{ value: "hold", label: "Normal hold" }, { value: "fraud", label: "Fraud hold" }]} />
            )}
          </div>
          <div inert className="rounded-card border border-line bg-raised p-2 select-none">
            <AccordionItem defaultOpen key={`${key}-${kind}`}
              header={
                <span className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="font-medium text-ink">{action.title}</span>
                  <span className="font-mono text-[12px] text-ink-3">{kind === "fraud" && action.fraudNote ? action.fraudNote : action.note}</span>
                </span>
              }
            >
              <div className="flex flex-col gap-4 pt-1">
                <Replica k={key} fraud={kind === "fraud" && !!action.fraudNote} loop={loop} />
              </div>
            </AccordionItem>
          </div>
        </div>
      </div>

      <div className="mt-8">
        <Shot {...SHOTS.review}
          alt="The Review page for sample 04 with Send to vendor open: both reasons ticked and the note drafted from the findings"
          caption={<>Sample 04 in Review. Send to vendor opens first because both findings are for the vendor; the reasons are ticked and the note is drafted from the numbers. <Link to="/review" className="text-ink underline underline-offset-2 hover:text-accent">Open the Review queue</Link></>} />
      </div>
    </Section>
  )
}

function whatHappens(key: Key, facts: HowFacts | undefined): ReactNode {
  const from = facts?.resume
  switch (key) {
    case "confirm":
      return <>Saves any fields you corrected, then runs the checks again from step {from?.confirm ?? "…"}, live on the Process page. A blank field means "not on the invoice", never a guess. It can't be used on a document that isn't an invoice.</>
    case "pick_po":
      return <>Matches the invoice to the PO you choose, then runs steps {from?.pick_po ?? "…"} to 9 again against it. The PO must be open, issued to this vendor, and dated on or before the invoice. Offered once the PO step has run.</>
    case "override":
      return <>Approves the invoice as it is. You must write why; the reason is kept in the history and shown on the decision. Draft emails that haven't gone out yet are discarded.</>
    case "send_to_vendor":
      return <>Tick what the vendor must fix; a note is drafted from the findings' own numbers. Check and edit the email, then send. The invoice waits on the vendor, and the email carries a {facts?.token_days ?? "…"}-day upload link.</>
    case "reject":
      return <>Closes the invoice as Rejected. You must write why; the reason is kept in the history. Draft emails that haven't gone out yet are discarded.</>
  }
}

function Who({ perm }: { perm: Permission }) {
  return (
    <div className="mt-1.5 flex flex-col gap-2 text-[15px] leading-relaxed">
      <p className="text-ink">{perm.rule === "anyone" ? "Any role." : perm.rule === "finance" ? "Finance only." : "Procurement only."} <span className="text-ink-2">{perm.why}</span></p>
      {perm.fraud && (
        <p className="rounded-input border border-reject/30 bg-reject-bg px-3.5 py-2.5 text-[14px] text-ink">
          <span className="font-mono text-[11px] font-medium tracking-[0.06em] text-reject uppercase">Fraud hold · </span>
          {perm.fraud_why}
        </p>
      )}
    </div>
  )
}

const Row = ({ children }: { children: ReactNode }) => <div className="flex flex-wrap items-center gap-3">{children}</div>
const Blocked = ({ children }: { children: ReactNode }) => (
  <p className="rounded-input border border-reject/30 bg-reject-bg px-4 py-3 text-[14px] leading-relaxed text-ink">{children}</p>
)

/** The same controls ReviewActions renders, with example values. Inert: nothing here can be clicked. */
function Replica({ k, fraud, loop }: { k: Key; fraud: boolean; loop: VendorLoop | undefined }) {
  const walk = useQuery({ queryKey: ["how", "po-walkthrough"], queryFn: getPoWalkthrough, staleTime: Infinity, enabled: k === "pick_po" })
  if (k === "confirm") {
    return (
      <>
        <Field label="Invoice date" htmlFor="rep-date" hint="Blank: not on the invoice. Sample 09 arrives like this.">
          <input id="rep-date" className={cn(inputCls, "max-w-xs font-mono text-[14px]")} placeholder="YYYY-MM-DD" readOnly />
        </Field>
        <p className="text-ink-2">Saves the fields above and runs the checks again from step 3. You'll watch it live on the Process page.</p>
        <Row><PillButton>Save and continue</PillButton></Row>
      </>
    )
  }
  if (k === "pick_po") {
    const scores = walk.data?.scores ?? []
    return (
      <>
        <div className="flex flex-wrap gap-2">
          {scores.map((o, i) => (
            <span key={o.po_id} className={cn("inline-flex h-10 items-center gap-2 rounded-full border bg-raised px-4 font-mono text-[13px] text-ink",
              i === 0 ? "border-ink" : "border-line")}>
              {o.po_id}<span className="num text-ink-3">{o.total.toFixed(1)}</span>
            </span>
          ))}
        </div>
        <label className="flex flex-col gap-1.5">
          <span className="label">PO number</span>
          <input readOnly value={scores[0]?.po_id ?? ""} className={cn(inputCls, "max-w-xs font-mono text-[14px]")} />
        </label>
        <p className="text-[14px] text-ink-2">Amounts, duplicates, tax and dates are checked again against this PO (steps 6 to 9).</p>
        <Row><PillButton>Use this PO</PillButton></Row>
        {scores.length > 0 && <p className="font-mono text-[11px] text-ink-3">Candidates and scores: sample 03's real score table.</p>}
      </>
    )
  }
  if (k === "override") {
    if (fraud) return <Blocked>This invoice has a fraud finding. Only Finance can clear it, after calling the vendor on the number on file. Switch the role to Finance to continue.</Blocked>
    return <ReasonReplica label="Why approve anyway?" placeholder="e.g. Extra 100 reams agreed with Procurement by email on 17 Sep" button="Approve invoice" />
  }
  if (k === "reject") {
    return <ReasonReplica label="Why reject?" placeholder="e.g. Vendor confirmed they never sent this invoice" button="Reject invoice" />
  }
  if (fraud) return <Blocked>There's a fraud finding, so nothing goes to the vendor. Finance verifies it by phone instead.</Blocked>
  return (
    <>
      <div className="flex flex-col gap-2">
        <span className="label">What the vendor needs to fix</span>
        <div className="flex flex-wrap gap-2">
          {(loop?.email.reasons ?? []).map((r) => (
            <span key={r.code} className="inline-flex h-10 items-center gap-2 rounded-full border border-ink bg-raised pr-4 pl-2 text-[14px] text-ink">
              <CodeChip code={r.code} tone="hold" />{r.title}
            </span>
          ))}
          <span className="inline-flex h-10 items-center rounded-full border border-line bg-raised px-4 text-[14px] text-ink-2">Other</span>
        </div>
      </div>
      <label className="flex flex-col gap-1.5">
        <span className="label">Note to the vendor (optional)</span>
        <textarea readOnly value={loop?.email.note ?? ""} rows={3} className={cn(inputCls, "h-auto py-3 text-[14px] leading-relaxed")} />
        <span className="text-[13px] text-ink-3">Drafted from the findings; edit it as you like.</span>
      </label>
      <Row><PillButton>Preview email</PillButton></Row>
      {loop && <p className="font-mono text-[11px] text-ink-3">Reasons and note: sample 04, drafted by the real templates.</p>}
    </>
  )
}

function ReasonReplica({ label, placeholder, button }: { label: string; placeholder: string; button: string }) {
  return (
    <>
      <label className="flex flex-col gap-1.5">
        <span className="label">{label}</span>
        <textarea readOnly placeholder={placeholder} rows={2} className={cn(inputCls, "h-auto py-3 leading-relaxed")} />
      </label>
      <Row><PillButton>{button}</PillButton></Row>
    </>
  )
}

/** Every built case that can end in Hold, by the step that raises it. */
function HoldSituations({ catalogue, onCase }: { catalogue: Catalogue | undefined; onCase: (code: string) => void }) {
  if (!catalogue) return <div className="h-64 animate-pulse rounded-card bg-hover" aria-busy />
  const holds = catalogue.cases.filter((c) => c.status === "Built" && (c.outcome === "Hold" || c.also === "Hold"))
  const stages = catalogue.stages
    .map((s) => ({ s, cases: holds.filter((c) => (c.runs_in ?? c.stage) === s.n) }))
    .filter((g) => g.cases.length)
  return (
    <div>
      <h3 className="text-h3">What puts an invoice on hold</h3>
      <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ink-2">
        {holds.length} situations in the case list can end in a Hold, plus any step that fails with a system error.
        Click a code to see the case in the 9 checks.
      </p>
      <div className="mt-5 overflow-hidden rounded-card border border-line bg-raised">
        {stages.map(({ s, cases }) => (
          <div key={s.n} className="grid gap-3 border-t border-line px-5 py-4 first:border-t-0 md:grid-cols-[200px_minmax(0,1fr)]">
            <p className="text-[14px] text-ink"><span className="font-mono text-[12px] text-ink-3">Step {s.n} · </span>{s.name}</p>
            <ul className="flex flex-wrap gap-x-4 gap-y-2">
              {cases.map((c) => (
                <li key={c.code}>
                  <button type="button" onClick={() => onCase(c.code)} aria-label={`Show case ${c.code}, ${c.title}, in the 9 checks`}
                    className="group inline-flex items-center gap-2 rounded-full text-left">
                    <CodeChip code={c.code} tone={c.fraud ? "reject" : "hold"} />
                    <span className="text-[14px] text-ink-2 group-hover:text-ink">{c.title}</span>
                    {c.fraud && <span className="font-mono text-[10px] font-medium tracking-[0.06em] text-reject uppercase">fraud</span>}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <p className="mt-3 text-[13px] text-ink-3">
        Each is emailed to whoever can fix it: e.g. <Alerted who={["Vendor"]} /> for a missing invoice number, <Alerted who={["Finance", "AP"]} fraud /> for a changed bank account.
      </p>
    </div>
  )
}
