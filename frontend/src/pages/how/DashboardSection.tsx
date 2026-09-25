import { useState, type ReactNode } from "react"
import { Link } from "react-router-dom"

import { inr } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { HowFacts, VendorLoop } from "@/types"
import { Section } from "./shared"
import { SHOTS } from "./shots"
import { Shot } from "./Shot"

type Kpi = { key: string; name: string; big: string; formula: ReactNode; example: ReactNode }

export function DashboardSection({ facts, loop }: { facts: HowFacts | undefined; loop: VendorLoop | undefined }) {
  const min = facts?.minutes_saved_per_invoice ?? 8
  const stepS = facts ? facts.min_stage_ms / 1000 : null
  const p = loop?.protected
  const kpis: Kpi[] = [
    {
      key: "touchless", name: "Touchless rate", big: "80%",
      formula: <>Invoices approved without anyone touching them, divided by invoices decided. "Touched" means any review action was logged on it.</>,
      example: <>10 invoices decided, 8 approved straight through: 8 ÷ 10 = 80%.</>,
    },
    {
      key: "money", name: "Money protected", big: p ? p.display : "…",
      formula: <>What holds and rejects stopped from being paid. Each run counts once, in the first category that fits: a rejected duplicate counts the whole invoice; else a fraud hold counts the whole invoice; else over-billing counts only the part above what was left on the PO. Approved runs count nothing.</>,
      example: loop && p ? <>Sample 04 bills {inr(loop.total_paise)} with {inr(loop.remaining_paise)} left on its PO, so {p.display} counts as over-billing blocked. If it's replaced by a corrected invoice, the original still counts (what it blocked stayed blocked) and the approved correction adds nothing.</> : "…",
    },
    {
      key: "time", name: "Time saved", big: `${min} min`,
      formula: <>Invoices decided × {min} minutes, an assumed figure for checking one invoice by hand. Shown in hours.</>,
      example: <>10 invoices × {min} min = {10 * min} min, or {Math.round((10 * min) / 6) / 10} hours.</>,
    },
    {
      key: "processing", name: "Avg processing time", big: "Seconds",
      formula: <>From upload until the run finished, averaged over finished runs. For an invoice re-checked after review, the clock runs until the re-check ends.</>,
      example: <>A clean invoice takes a few seconds. The live view holds each of the 10 steps for at least {stepS ?? "…"} s so you can watch it, so about {stepS != null ? Math.round(stepS * 10) : "…"} s is the floor here.</>,
    },
    {
      key: "reasons", name: "Top hold reasons", big: `Top ${facts?.top_reasons ?? 8}`,
      formula: <>Among held and rejected invoices, how many carried each case code. A code counts once per invoice, however many lines it hit.</>,
      example: <>Sample 04 adds one to 6.5 (over PO balance) and one to 6.6 (quantity above ordered).</>,
    },
    {
      key: "health", name: "Health", big: "4 signals",
      formula: <>Share of invoices with a low-confidence reading (2.2); share with a system error; average AI calls per run; average time per step.</>,
      example: <>A run read from the saved answer makes 0 AI calls; a brand-new file makes up to {facts?.max_llm_calls ?? "…"}. A rising system-error share means something needs fixing.</>,
    },
  ]
  const [on, setOn] = useState(kpis[1].key)
  const k = kpis.find((x) => x.key === on)!

  return (
    <Section
      id="dashboard"
      kicker="13 · Dashboard"
      title="What the numbers mean"
      lede="The Dashboard adds up real runs only: the seed history of earlier invoices is left out. Pick a number to see its formula in plain words."
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <ul className="grid gap-2 sm:grid-cols-2">
          {kpis.map((x) => (
            <li key={x.key}>
              <button type="button" aria-pressed={on === x.key} onClick={() => setOn(x.key)}
                className={cn(
                  "flex h-full w-full flex-col items-start gap-2 rounded-card border bg-raised p-4 text-left transition-colors duration-200",
                  on === x.key ? "border-ink" : "border-line hover:border-ink-3",
                )}>
                <span className="label">{x.name}</span>
                <span className="num font-mono text-[22px] leading-none font-semibold tracking-tight text-ink">{x.big}</span>
              </button>
            </li>
          ))}
        </ul>
        <div className="flex flex-col gap-4 rounded-card border border-line bg-raised p-5" aria-live="polite">
          <p className="text-h3">{k.name}</p>
          <div>
            <p className="label">Formula</p>
            <p className="mt-1.5 text-[15px] leading-relaxed text-ink">{k.formula}</p>
          </div>
          <div className="rounded-[14px] bg-bubble px-4 py-3">
            <p className="label">Example</p>
            <p className="mt-1 font-mono text-[13px] leading-[1.6] text-ink">{k.example}</p>
          </div>
        </div>
      </div>
      <p className="mt-3 text-[13px] text-ink-3">
        The big numbers above are examples, except money protected, which is sample 04 run just now. A replaced invoice
        isn't counted as a decision: its correction is.
      </p>

      <div className="mt-8">
        <Shot {...SHOTS.dashboard}
          alt="The Dashboard after running samples 01, 03, 04 and 06: counts, touchless rate, money protected and charts"
          caption={<>The Dashboard after samples 01, 03, 04 and 06. <Link to="/dashboard" className="text-ink underline underline-offset-2 hover:text-accent">Open the Dashboard</Link></>} />
      </div>
    </Section>
  )
}
