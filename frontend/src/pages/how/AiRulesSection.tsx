import { useState } from "react"

import { cn } from "@/lib/utils"
import type { Catalogue } from "@/types"
import { AiBadge, Section, Segmented } from "./shared"

type Side = "ai" | "rules"
type Job = { side: Side; name: string; step: string; why: string }

const JOBS: Job[] = [
  { side: "ai", name: "Reading the invoice", step: "Step 2",
    why: "Every vendor's layout is different, and some are scans. The AI fills one fixed form, says what kind of document it is, and flags any field it isn't sure about." },
  { side: "ai", name: "Comparing item descriptions", step: "Step 5",
    why: "“ErgoPro Mesh Chair” and “Ergonomic office chair, mesh back” are the same thing in different words. The AI only returns how alike they are, from 0 to 1." },
  { side: "rules", name: "Maths", step: "Step 3", why: "Lines must add up to the subtotal, and subtotal plus tax to the total, within ₹1 for rounding." },
  { side: "rules", name: "Balances", step: "Step 6", why: "What's left on a PO is its total minus the invoices already approved against it. Worked out fresh every time." },
  { side: "rules", name: "Tolerance", step: "Step 6", why: "How close is close enough: a percentage capped at a rupee amount, set by Finance in Settings." },
  { side: "rules", name: "Duplicates", step: "Step 7", why: "The same file, number, amount or date as an earlier invoice from the same vendor." },
  { side: "rules", name: "Tax", step: "Step 8", why: "Which GST applies follows from two state codes; the rate must be on the PO and valid on the invoice date." },
  { side: "rules", name: "Dates", step: "Step 9", why: "Due date is the invoice date plus the PO's terms, capped at 45 days for small businesses." },
  { side: "rules", name: "Picking the PO", step: "Step 5", why: "Filters and a 100-point score decide the match. The AI's similarity is one input, never the answer." },
  { side: "rules", name: "Writing the emails", step: "Alerts", why: "Emails are filled from templates with the findings' own sentences, so they say exactly what the checks found." },
  { side: "rules", name: "The decision", step: "Decision", why: "Any Reject makes it Reject, else any Hold makes it Hold, else Approve. Never a model's opinion." },
]

export function AiRulesSection({ catalogue }: { catalogue: Catalogue | undefined }) {
  const [side, setSide] = useState<Side>("ai")
  const [job, setJob] = useState<Job>(JOBS[0])
  const maxCalls = catalogue?.rules.max_llm_calls
  const pickSide = (s: Side) => {
    setSide(s)
    setJob(JOBS.find((j) => j.side === s)!)
  }

  return (
    <Section
      id="ai"
      kicker="04 · AI vs rules"
      title="AI reads, rules decide"
      lede="The AI is used where text is messy. Everything that decides money is a written rule, so the same invoice always gets the same answer, and every answer can be explained."
    >
      <Segmented label="Show jobs done by" value={side} onChange={pickSide}
        options={[{ value: "ai", label: "What the AI does" }, { value: "rules", label: "What rules do" }]} />

      <div className="mt-5 grid gap-3 md:grid-cols-2">
        {(["ai", "rules"] as Side[]).map((s) => {
          const on = side === s
          return (
            <div key={s} className={cn(
              "rounded-card border p-5 transition-[opacity,border-color] duration-200",
              on ? "border-ink bg-raised" : "border-line bg-transparent opacity-55",
            )}>
              <div className="flex items-center gap-3">
                <AiBadge ai={s === "ai"} />
                <span className="text-[15px] font-medium text-ink">{s === "ai" ? "2 jobs" : `${JOBS.filter((j) => j.side === "rules").length} jobs`}</span>
              </div>
              <ul className="mt-4 flex flex-wrap gap-2">
                {JOBS.filter((j) => j.side === s).map((j) => (
                  <li key={j.name}>
                    <button
                      type="button"
                      aria-pressed={job === j}
                      onClick={() => { setSide(s); setJob(j) }}
                      className={cn(
                        "h-9 rounded-full border px-3.5 text-[14px] transition-colors duration-200",
                        job === j ? "border-ink bg-ink text-white" : "border-line bg-raised text-ink hover:border-ink",
                      )}
                    >
                      {j.name}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )
        })}
      </div>

      <div aria-live="polite" className="mt-4 rounded-card bg-bubble px-5 py-4">
        <p className="label">{job.step} · {job.name}</p>
        <p className="mt-1.5 font-mono text-[14px] leading-[1.6] text-ink">{job.why}</p>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        <Fact big={maxCalls != null ? `≤ ${maxCalls}` : "…"} small="AI calls per invoice: one to read it, one to compare descriptions." />
        <Fact big="₹0" small="to run the same file again: both answers are saved, so a re-run never asks the AI twice." />
        <Fact big="Never" small="crashes on an AI error. Unreadable → a person enters it. Comparison down → plain text matching, marked lower confidence." />
      </div>
    </Section>
  )
}

function Fact({ big, small }: { big: string; small: string }) {
  return (
    <div className="rounded-card border border-line bg-raised p-5">
      <p className="num font-mono text-[28px] leading-none font-semibold tracking-tight text-ink">{big}</p>
      <p className="mt-2 text-[14px] leading-snug text-ink-2">{small}</p>
    </div>
  )
}
