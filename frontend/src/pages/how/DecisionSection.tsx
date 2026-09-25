import { useState } from "react"
import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"

import { getSettings } from "@/api"
import { PixelMascot, type MascotState } from "@/components/brand/PixelMascot"
import { DecisionStamp } from "@/components/ds/DecisionStamp"
import { inputCls } from "@/components/ds/Field"
import { CodeChip } from "@/components/ds/StatusChip"
import { inr } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { Catalogue, CatalogueCase, Decision } from "@/types"
import { AUDIENCE_LABEL } from "./labels"
import { CaseCodeChip, OutcomeChip, Section } from "./shared"

// Findings to toggle in the toy: one of each kind, all real cases.
const TOY = ["4.1", "9.5", "6.5", "4.7", "7.2"]
const MOOD: Record<Decision, MascotState> = { Approve: "approved", Hold: "hold", Reject: "reject" }

/** The same precedence as backend/app/pipeline/decide.py. */
function decide(outcomes: string[]): Decision {
  return outcomes.includes("Reject") ? "Reject" : outcomes.includes("Hold") ? "Hold" : "Approve"
}

export function DecisionSection({ catalogue, onCase }: { catalogue: Catalogue | undefined; onCase: (code: string) => void }) {
  const byCode = new Map((catalogue?.cases ?? []).map((c) => [c.code, c]))
  const toy = TOY.map((c) => byCode.get(c)).filter((c): c is CatalogueCase => !!c)
  const [on, setOn] = useState<Set<string>>(new Set(["4.1", "6.5"]))
  const picked = toy.filter((c) => on.has(c.code))
  const decision = decide(picked.map((c) => c.outcome))
  const rung = decision === "Reject" ? 0 : decision === "Hold" ? 1 : 2
  const toggle = (code: string) => setOn((s) => {
    const n = new Set(s)
    if (n.has(code)) n.delete(code)
    else n.add(code)
    return n
  })

  return (
    <Section
      id="decision"
      kicker="06 · The decision"
      title="How the decision is made"
      lede="Each check leaves findings. Then one short rule turns them into Approve, Hold or Reject. Switch findings on and off to see it work."
    >
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="rounded-card border border-line bg-raised p-5">
          <p className="label">Findings on this made-up invoice</p>
          <ul className="mt-3 flex flex-col gap-2">
            {toy.map((c) => (
              <li key={c.code}>
                <label className={cn(
                  "flex cursor-pointer items-center gap-3 rounded-[14px] border px-3 py-2.5 transition-colors duration-200 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent",
                  on.has(c.code) ? "border-ink bg-raised" : "border-line bg-transparent opacity-60 hover:opacity-100",
                )}>
                  <input type="checkbox" className="sr-only" checked={on.has(c.code)} onChange={() => toggle(c.code)} />
                  <span aria-hidden className={cn("grid size-4 place-items-center rounded-[4px] border text-[10px]", on.has(c.code) ? "border-ink bg-ink text-white" : "border-ink-3")}>
                    {on.has(c.code) ? "✓" : ""}
                  </span>
                  <CaseCodeChip c={c} />
                  <span className="flex-1 text-[14px] text-ink">{c.title}</span>
                  <OutcomeChip outcome={c.outcome} />
                </label>
              </li>
            ))}
          </ul>
        </div>

        <div className="flex flex-col gap-4 rounded-card border border-line bg-raised p-5">
          <ol className="flex flex-col gap-2">
            {[
              ["Any Reject?", "Reject"],
              ["Otherwise, any Hold?", "Hold"],
              ["Otherwise", "Approve"],
            ].map(([q, a], i) => (
              <li key={a} className={cn(
                "flex items-center justify-between rounded-full border px-4 py-2 font-mono text-[13px] transition-colors duration-200",
                rung === i ? "border-ink bg-ink text-white" : i < rung ? "border-line text-ink-3 line-through" : "border-line text-ink-3",
              )}>
                <span>{q}</span>
                <span>→ {a}</span>
              </li>
            ))}
          </ol>
          <div className="flex items-center gap-4 pt-2" aria-live="polite">
            <PixelMascot state={MOOD[decision]} size={56} />
            <DecisionStamp decision={decision} />
          </div>
          <p className="text-[13px] leading-relaxed text-ink-2">
            Info findings (like a small business's shorter due date) never change the decision. They're notes for whoever pays.
          </p>
        </div>
      </div>

      <Tolerance onCase={onCase} />
      <AfterDecision catalogue={catalogue} />
    </Section>
  )
}

function Tolerance({ onCase }: { onCase: (code: string) => void }) {
  const settings = useQuery({ queryKey: ["settings"], queryFn: getSettings })
  const [raw, setRaw] = useState("100000")
  const pct = settings.data?.tolerance_pct
  const cap = settings.data?.tolerance_cap_paise
  const rupees = Number(raw.replace(/[,\s₹]/g, ""))
  const valid = raw.trim() !== "" && Number.isFinite(rupees) && rupees >= 0
  const paise = valid ? Math.round(rupees * 100) : 0
  const pctPart = pct != null ? Math.round((paise * pct) / 100) : 0
  const allowed = cap != null ? Math.min(pctPart, cap) : pctPart
  const capped = cap != null && pctPart > cap

  return (
    <div className="mt-10">
      <h3 className="text-h3">Close enough? The tolerance</h3>
      <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ink-2">
        Prices and totals can differ a little for honest reasons, like rounding. The allowed difference is{" "}
        {pct != null && cap != null ? <b className="font-medium text-ink">{pct}% of the amount, capped at {inr(cap)}</b> : "a percentage with a cap"},
        from the current Settings. Only Finance can change it.
      </p>
      <div className="mt-5 grid gap-5 rounded-card border border-line bg-raised p-5 md:grid-cols-[260px_minmax(0,1fr)]">
        <div className="flex flex-col gap-2">
          <label htmlFor="tol-amount" className="label">Amount on the PO (₹)</label>
          <input id="tol-amount" inputMode="decimal" value={raw} onChange={(e) => setRaw(e.target.value)} className={cn(inputCls, "num font-mono")} />
          <div className="flex flex-wrap gap-1.5">
            {[10000, 100000, 500000].map((v) => (
              <button key={v} type="button" onClick={() => setRaw(String(v))}
                className="h-7 rounded-full border border-line px-2.5 font-mono text-[11px] text-ink-2 hover:border-ink">
                {inr(v * 100)}
              </button>
            ))}
          </div>
        </div>
        <div aria-live="polite">
          {!valid ? (
            <p className="text-[14px] text-hold">Type an amount in rupees, like 1,18,000.</p>
          ) : settings.isError ? (
            <p className="text-[14px] text-hold">Couldn't load the settings.</p>
          ) : (
            <>
              <p className="label">Allowed difference</p>
              <p className="num mt-1 font-mono text-[32px] leading-none font-semibold text-ink">± {inr(allowed)}</p>
              <p className="mt-2 text-[14px] text-ink-2">
                {pct}% of {inr(paise)} is {inr(pctPart)}{capped ? `, over the ${inr(cap)} cap, so the cap applies.` : ", under the cap."}
              </p>
              <div className="relative mt-5 h-8" aria-hidden>
                <div className="absolute top-1/2 right-0 left-0 h-px bg-line" />
                <div className="absolute top-1/2 h-3 -translate-y-1/2 rounded-full bg-approve-bg ring-1 ring-approve/40" style={{ left: "25%", right: "25%" }} />
                <div className="absolute top-0 bottom-0 left-1/2 w-px bg-ink" />
              </div>
              <div className="num grid grid-cols-3 font-mono text-[12px] text-ink-2">
                <span className="text-left">{inr(paise - allowed)}</span>
                <span className="text-center text-ink">{inr(paise)}</span>
                <span className="text-right">{inr(paise + allowed)}</span>
              </div>
              <p className="mt-1 text-[13px] text-ink-3">Anything in the green band passes.</p>
            </>
          )}
        </div>
      </div>
      <p className="mt-3 flex flex-wrap items-center gap-1.5 text-[13px] text-ink-2">
        Used by
        {["6.2", "6.3", "6.5", "6.7"].map((c) => (
          <button key={c} type="button" onClick={() => onCase(c)} className="rounded-full" aria-label={`Show case ${c}`}><CodeChip code={c} /></button>
        ))}
        and the balance filter when finding a PO.
      </p>
    </div>
  )
}

function AfterDecision({ catalogue }: { catalogue: Catalogue | undefined }) {
  const cases = catalogue?.cases ?? []
  const count = (a: string) => cases.filter((c) => c.status === "Built" && (c.alerted as string[]).includes(a)).length
  const cards = [
    {
      id: "after-alerts", title: "Alerts",
      body: "One email per audience, listing every issue at once. Vendor mistakes go to the vendor, our side to Procurement, judgement calls to the AP team, fraud to Finance and AP. Never the vendor on fraud.",
      extra: catalogue && (
        <ul className="mt-3 flex flex-wrap gap-1.5 font-mono text-[11px] text-ink-2">
          {(["Vendor", "AP", "Procurement", "Finance"] as const).map((a) => (
            <li key={a} className="rounded-full bg-hover px-2.5 py-1">{AUDIENCE_LABEL[a]} · {count(a)} cases</li>
          ))}
        </ul>
      ),
    },
    {
      id: "after-review", title: "Review",
      body: "Held invoices wait in the Review queue. A person can correct a field, pick the PO, override, send it back to the vendor or reject it. Only Finance can clear a fraud hold.",
      extra: <Link to="/review" className="mt-3 inline-block font-mono text-[12px] text-ink underline underline-offset-2 hover:text-accent">Open the Review queue</Link>,
    },
    {
      id: "after-vendor", title: "Vendor fix",
      body: "When the vendor must fix something, their email carries a private link to upload a corrected invoice. No login needed.",
    },
    {
      id: "after-recheck", title: "Re-check",
      body: "A corrected invoice runs through all 9 checks again as a new run. It replaces the held one, so nothing is counted twice.",
    },
  ]
  return (
    <div className="mt-10">
      <h3 className="text-h3">After the decision</h3>
      <p className="mt-2 text-[14px] text-ink-2">In this demo every email lands in the owner's inbox, with the real recipient written at the top.</p>
      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        {cards.map((c, i) => (
          <div key={c.id} id={c.id} tabIndex={-1} className="scroll-mt-28 rounded-card border border-line bg-raised p-5 outline-none focus-visible:ring-2 focus-visible:ring-accent">
            <p className="label">{String(i + 1).padStart(2, "0")}</p>
            <h4 className="mt-1 text-[17px] font-medium text-ink">{c.title}</h4>
            <p className="mt-1.5 text-[14px] leading-relaxed text-ink-2">{c.body}</p>
            {c.extra}
          </div>
        ))}
      </div>
    </div>
  )
}
