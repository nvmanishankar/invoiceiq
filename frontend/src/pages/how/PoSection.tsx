import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { motion, useReducedMotion } from "motion/react"

import { getPoWalkthrough } from "@/api"
import { PillButton } from "@/components/ds/PillButton"
import { CodeChip, StatusChip } from "@/components/ds/StatusChip"
import { day, inr, qty } from "@/lib/format"
import { EASE_OUT } from "@/lib/motion"
import { cn } from "@/lib/utils"
import type { PoWalkthrough } from "@/types"
import { Section, Segmented, TryIt } from "./shared"

const STEPS = ["Filter", "Score", "Decide"] as const

const WHY: Record<string, (reason: string) => string> = {
  Vendor: (r) => `Another vendor (${r})`,
  Status: (r) => `PO is ${r.toLowerCase()}`,
  Balance: (r) => r,
  Date: (r) => r,
}

export function PoSection() {
  const q = useQuery({ queryKey: ["how", "po-walkthrough"], queryFn: getPoWalkthrough, staleTime: Infinity })
  const [step, setStep] = useState(0)
  const [replay, setReplay] = useState(0)
  const w = q.data

  return (
    <Section
      id="po"
      kicker="05 · Finding the PO"
      title="How the PO is found"
      lede="A purchase order (PO) is the company's own record of what it agreed to buy. When an invoice doesn't say which PO it's for, rules work it out. This is sample 03, run through the real checks just now."
    >
      {q.isError && <p role="alert" className="text-hold">Couldn't load the walkthrough. Is the API running?</p>}
      {!w && !q.isError && <div className="h-80 animate-pulse rounded-card bg-hover" aria-busy />}
      {w && (
        <div className="flex flex-col gap-5">
          <InvoiceCard w={w} />

          <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Walkthrough step">
            {STEPS.map((s, i) => (
              <button key={s} type="button" aria-current={step === i ? "step" : undefined} onClick={() => setStep(i)}
                className={cn(
                  "flex h-9 items-center gap-2 rounded-full border px-3.5 font-mono text-[12px] transition-colors duration-200",
                  step === i ? "border-ink bg-ink text-white" : step > i ? "border-ink bg-raised text-ink" : "border-line bg-raised text-ink-3 hover:border-ink-3",
                )}>
                <span>{i + 1}</span>
                <span>{s}</span>
              </button>
            ))}
            {step === 0 && (
              <button type="button" onClick={() => setReplay((r) => r + 1)} className="ml-auto font-mono text-[12px] text-ink-2 underline underline-offset-2 hover:text-accent">
                Replay
              </button>
            )}
          </div>

          <div className="min-h-[420px] rounded-card border border-line bg-raised p-5 md:p-6">
            {step === 0 && <FilterStep key={replay} w={w} />}
            {step === 1 && <ScoreStep w={w} />}
            {step === 2 && <RuleStep w={w} />}
          </div>

          <div className="flex items-center gap-3">
            <PillButton variant="secondary" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>Back</PillButton>
            {step < STEPS.length - 1
              ? <PillButton onClick={() => setStep((s) => s + 1)}>Next: {STEPS[step + 1].toLowerCase()}</PillButton>
              : <TryIt sample={w.sample} />}
            <span className="ml-auto font-mono text-[12px] text-ink-3">Step {step + 1} of {STEPS.length}</span>
          </div>
        </div>
      )}
    </Section>
  )
}

function InvoiceCard({ w }: { w: PoWalkthrough }) {
  const inv = w.invoice
  return (
    <div className="grid gap-4 rounded-card bg-bubble p-5 sm:grid-cols-[auto_minmax(0,1fr)]">
      <div>
        <p className="label">The invoice</p>
        <p className="mt-1 font-mono text-[15px] text-ink">{inv.invoice_no}</p>
      </div>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-[14px] md:grid-cols-4">
        <div><dt className="label">Vendor</dt><dd className="text-ink">{inv.vendor}</dd></div>
        <div><dt className="label">Date</dt><dd className="text-ink">{day(inv.invoice_date)}</dd></div>
        <div><dt className="label">Total</dt><dd className="num text-ink">{inr(inv.total_paise)}</dd></div>
        <div><dt className="label">PO number</dt><dd className="text-hold">{inv.po_reference ?? "None printed"}</dd></div>
        <div className="col-span-2 md:col-span-4">
          <dt className="label">Items</dt>
          <dd className="text-ink">{inv.lines.map((l) => `${qty(l.qty)} × ${l.description} at ${inr(l.unit_price_paise)}`).join("; ")}</dd>
        </div>
      </dl>
    </div>
  )
}

function FilterStep({ w }: { w: PoWalkthrough }) {
  const reduce = useReducedMotion()
  // Survivors first stay put; eliminated POs fade out one by one, in the order the filters run.
  const order = ["Vendor", "Status", "Balance", "Date"]
  const rows = [...w.elimination].sort((a, b) =>
    (a.eliminated_by ? order.indexOf(a.eliminated_by) : 9) - (b.eliminated_by ? order.indexOf(b.eliminated_by) : 9))
  const survivors = rows.filter((r) => !r.eliminated_by).length
  const by = (f: string) => rows.filter((r) => r.eliminated_by === f).length
  return (
    <div>
      <p className="text-[15px] leading-relaxed text-ink">
        Four yes/no filters run on every PO: <b className="font-medium">same vendor</b>, <b className="font-medium">still open</b>,{" "}
        <b className="font-medium">enough balance left</b> and <b className="font-medium">raised before the invoice</b>.
      </p>
      <ul className="mt-3 flex flex-wrap gap-2 font-mono text-[12px] text-ink-2">
        {order.map((f) => <li key={f} className="rounded-full bg-hover px-3 py-1">{f}: −{by(f)}</li>)}
        <li className="rounded-full bg-approve-bg px-3 py-1 text-approve">{rows.length} POs → {survivors} left</li>
      </ul>
      <ol className="mt-5 flex flex-col divide-y divide-line">
        {rows.map((r, i) => {
          const out = !!r.eliminated_by
          return (
            <motion.li
              key={r.po_id}
              initial={{ opacity: 1 }}
              animate={{ opacity: out ? 0.38 : 1 }}
              transition={reduce ? { duration: 0 } : { delay: out ? 0.3 + i * 0.12 : 0, duration: 0.35, ease: EASE_OUT }}
              className="grid grid-cols-[110px_minmax(0,1fr)_auto] items-center gap-3 py-2.5 text-[14px]"
            >
              <span className={cn("font-mono text-[13px]", out ? "text-ink-2 line-through" : "font-medium text-ink")}>{r.po_id}</span>
              <span className="truncate text-ink-2">
                {r.po ? `${r.po.vendor} · ${day(r.po.po_date)} · ${inr(r.po.remaining_paise)} left` : ""}
              </span>
              {out
                ? <span className="font-mono text-[11.5px] text-ink-2">{WHY[r.eliminated_by!]?.(r.reason) ?? r.reason}</span>
                : <StatusChip status="pass" word="Survives" />}
            </motion.li>
          )
        })}
      </ol>
    </div>
  )
}

function ScoreStep({ w }: { w: PoWalkthrough }) {
  const reduce = useReducedMotion()
  const weights = w.rules.po_weights
  const signals = [
    { key: "lines", label: "Items", max: weights.lines, hint: "Same things, in quantities and at prices the PO allows?" },
    { key: "amount", label: "Amount", max: weights.amount, hint: "How closely the total fits what's left on the PO." },
    { key: "date", label: "Date", max: weights.date, hint: "How soon after the PO the invoice came." },
  ] as const
  return (
    <div>
      <p className="text-[15px] leading-relaxed text-ink">
        Each PO that survives gets up to 100 points: {signals.map((s, i) => (
          <span key={s.key}>{i ? (i === signals.length - 1 ? " and " : ", ") : ""}<b className="font-medium">{s.label.toLowerCase()} {s.max}</b></span>
        ))}.
      </p>
      <dl className="mt-3 grid gap-2 text-[13px] text-ink-2 sm:grid-cols-3">
        {signals.map((s) => <div key={s.key}><dt className="label">{s.label} · {s.max}</dt><dd>{s.hint}</dd></div>)}
      </dl>
      <ol className="mt-6 flex flex-col gap-5">
        {w.scores.map((sc, row) => {
          const top = sc.po_id === w.top
          return (
            <li key={sc.po_id}>
              <div className="flex items-baseline justify-between">
                <span className={cn("font-mono text-[14px]", top ? "font-semibold text-ink" : "text-ink-2")}>{sc.po_id}</span>
                <span className="num font-mono text-[20px] font-semibold text-ink">{sc.total.toFixed(1)}</span>
              </div>
              <div className="mt-2 grid gap-1.5">
                {signals.map((s, i) => {
                  const v = sc[s.key]
                  return (
                    <div key={s.key} className="grid grid-cols-[64px_minmax(0,1fr)_72px] items-center gap-3">
                      <span className="font-mono text-[11px] text-ink-3">{s.label}</span>
                      <span className="relative h-2.5 overflow-hidden rounded-full bg-hover" style={{ width: `${(s.max / 50) * 100}%` }}>
                        <motion.span
                          className={cn("absolute inset-y-0 left-0 rounded-full", top ? "bg-accent" : "bg-ink-2")}
                          initial={{ width: reduce ? `${(v / s.max) * 100}%` : "0%" }}
                          animate={{ width: `${(v / s.max) * 100}%` }}
                          transition={reduce ? { duration: 0 } : { delay: 0.15 + row * 0.25 + i * 0.1, duration: 0.6, ease: EASE_OUT }}
                        />
                      </span>
                      <span className="num text-right font-mono text-[12px] text-ink-2">{v.toFixed(1)} / {s.max}</span>
                    </div>
                  )
                })}
              </div>
            </li>
          )
        })}
      </ol>
      {w.explanation && (
        <p className="mt-6 border-l-[3px] border-accent pl-4 text-[14px] leading-relaxed text-ink">{w.explanation}</p>
      )}
    </div>
  )
}

type Scenario = "run" | "close" | "weak"

function verdict(top: number, second: number, minScore: number, minGap: number) {
  if (top >= minScore && top - second >= minGap) return { code: "5.7", word: "Match", tone: "pass" as const, text: "Matched automatically, marked “inferred”, with the evidence shown." }
  if (top >= minScore) return { code: "5.8", word: "Hold", tone: "warn" as const, text: "Two POs fit about equally well. It's held, and the AP team picks one." }
  return { code: "5.9", word: "Hold", tone: "warn" as const, text: "No PO fits well enough. It's held, and the vendor is asked for the PO number." }
}

function RuleStep({ w }: { w: PoWalkthrough }) {
  const [scenario, setScenario] = useState<Scenario>("run")
  const { po_match_min_score: minScore, po_match_min_gap: minGap } = w.rules
  const [a, b] = w.scores
  const real = { top: a?.total ?? 0, second: b?.total ?? 0, topId: a?.po_id ?? "—", secondId: b?.po_id ?? "—" }
  const cases: Record<Scenario, typeof real> = {
    run: real,
    close: { ...real, top: minScore + 8, second: minScore + 1 },
    weak: { ...real, top: minScore - 12, second: minScore - 35 },
  }
  const s = cases[scenario]
  const gap = +(s.top - s.second).toFixed(1)
  const v = verdict(s.top, s.second, minScore, minGap)
  const okScore = s.top >= minScore
  const okGap = gap >= minGap

  return (
    <div>
      <p className="text-[15px] leading-relaxed text-ink">
        The rule: the top PO must score <b className="font-medium">at least {minScore}</b> and be <b className="font-medium">ahead by {minGap} or more</b>.
        Then it's a match. Otherwise a person is asked. A wrong confident match is worse than a short wait.
      </p>
      <div className="mt-4">
        <Segmented label="Scores to test" value={scenario} onChange={setScenario} options={[
          { value: "run", label: "Sample 03, as run" },
          { value: "close", label: "What if: close race" },
          { value: "weak", label: "What if: weak scores" },
        ]} />
      </div>

      {/* 0-100 number line */}
      <div className="relative mt-10 mb-12 h-2 rounded-full bg-hover" aria-hidden>
        <div className="absolute inset-y-0 right-0 rounded-r-full bg-approve-bg" style={{ left: `${minScore}%` }} />
        <div className="absolute -top-3 -bottom-3 w-px bg-ink" style={{ left: `${minScore}%` }} />
        <span className="absolute -top-8 -translate-x-1/2 font-mono text-[11px] text-ink" style={{ left: `${minScore}%` }}>{minScore}</span>
        <div className="absolute top-4 h-2 border-x border-b border-ink-3" style={{ left: `${s.second}%`, width: `${Math.max(0, gap)}%` }} />
        <span className="absolute top-7 -translate-x-1/2 font-mono text-[11px] text-ink-2" style={{ left: `${(s.top + s.second) / 2}%` }}>gap {gap}</span>
        {[{ id: s.secondId, v: s.second, top: false }, { id: s.topId, v: s.top, top: true }].map((d) => (
          <motion.span key={d.top ? "t" : "s"} layout className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2" style={{ left: `${d.v}%` }}>
            <span className={cn("block size-4 rounded-full border-2 border-raised", d.top ? "bg-accent" : "bg-ink-2")} />
          </motion.span>
        ))}
        <span className="absolute -bottom-9 left-0 font-mono text-[11px] text-ink-3">0</span>
        <span className="absolute right-0 -bottom-9 font-mono text-[11px] text-ink-3">100</span>
      </div>

      <ul className="grid gap-2 sm:grid-cols-2">
        <Check ok={okScore} text={`Top score ${s.top.toFixed(1)} (${s.topId}) ${okScore ? "≥" : "<"} ${minScore}`} />
        <Check ok={okGap} text={`Ahead of ${s.secondId} by ${gap} ${okGap ? "≥" : "<"} ${minGap}`} />
      </ul>

      <div aria-live="polite" className="mt-5 flex flex-wrap items-center gap-3 rounded-card bg-bubble px-5 py-4">
        <CodeChip code={v.code} tone={v.tone === "pass" ? "pass" : "hold"} />
        <StatusChip status={v.tone} word={v.word} />
        <p className="font-mono text-[14px] leading-[1.6] text-ink">{v.text}</p>
        {scenario === "run" && w.matched_po && (
          <p className="w-full font-mono text-[12px] text-ink-2">
            Real result: {w.matched_po}, {w.match_type.toLowerCase()}, {w.match_confidence?.toLowerCase()} confidence. The invoice was {w.decision === "Approve" ? "approved" : w.decision?.toLowerCase()}.
          </p>
        )}
        {scenario !== "run" && <p className="w-full font-mono text-[12px] text-ink-3">Made-up scores, same rule.</p>}
      </div>
    </div>
  )
}

function Check({ ok, text }: { ok: boolean; text: string }) {
  return (
    <li className={cn("flex items-center gap-2.5 rounded-full border px-4 py-2 font-mono text-[13px]", ok ? "border-approve/30 bg-approve-bg text-approve" : "border-hold/30 bg-hold-bg text-hold")}>
      <span aria-hidden>{ok ? "✓" : "✗"}</span>
      <span>{text}</span>
    </li>
  )
}
