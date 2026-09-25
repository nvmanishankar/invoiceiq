import { useEffect, useRef, type KeyboardEvent } from "react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"

import { cn } from "@/lib/utils"
import type { Catalogue, CatalogueCase } from "@/types"
import { AiBadge, Alerted, BuiltBadge, CaseCodeChip, OutcomeChip, Section, Segmented, TryIt } from "./shared"

export type Filter = "all" | "holds" | "rejects" | "fraud" | "built"

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "holds", label: "Holds" },
  { value: "rejects", label: "Rejects" },
  { value: "fraud", label: "Fraud" },
  { value: "built", label: "Built only" },
]

const has = (c: CatalogueCase, o: string) => c.outcome === o || c.also === o
const MATCH: Record<Filter, (c: CatalogueCase) => boolean> = {
  all: () => true,
  holds: (c) => has(c, "Hold"),
  rejects: (c) => has(c, "Reject"),
  fraud: (c) => c.fraud,
  built: (c) => c.status === "Built",
}

export function ChecksSection({ catalogue, stage, setStage, filter, setFilter, focusCode }: {
  catalogue: Catalogue | undefined
  stage: number
  setStage: (n: number) => void
  filter: Filter
  setFilter: (f: Filter) => void
  focusCode: { code: string; at: number } | null
}) {
  const reduce = useReducedMotion()
  const tabs = useRef<(HTMLButtonElement | null)[]>([])
  const stages = catalogue?.stages ?? []
  const cases = catalogue?.cases ?? []
  const shown = cases.filter(MATCH[filter])
  const countIn = (n: number) => shown.filter((c) => c.stage === n).length
  const current = stages.find((s) => s.n === stage)
  const here = shown.filter((c) => c.stage === stage)

  const pickFilter = (f: Filter) => {
    setFilter(f)
    const matches = cases.filter(MATCH[f])
    if (!matches.some((c) => c.stage === stage) && matches.length) setStage(matches[0].stage)
  }

  const onTabKey = (e: KeyboardEvent, i: number) => {
    const n = stages.length
    const next = e.key === "ArrowRight" ? (i + 1) % n : e.key === "ArrowLeft" ? (i - 1 + n) % n
      : e.key === "Home" ? 0 : e.key === "End" ? n - 1 : null
    if (next === null) return
    e.preventDefault()
    setStage(stages[next].n)
    tabs.current[next]?.focus()
  }

  return (
    <Section
      id="checks"
      kicker="03 · The 9 checks"
      title="The 9 checks"
      lede="Every invoice goes through all nine, in order, even after a problem is found, so one email can list every issue. Only steps 1 and 2 can stop early: if the file can't be read, there's nothing to check."
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Segmented label="Filter cases" options={FILTERS} value={filter} onChange={pickFilter} />
        <p className="font-mono text-[12px] text-ink-3" aria-live="polite">{shown.length} of {cases.length} cases</p>
      </div>

      <div role="tablist" aria-label="Checks" className="mt-5 grid grid-cols-3 gap-2 sm:grid-cols-9">
        {stages.map((s, i) => {
          const active = s.n === stage
          const count = countIn(s.n)
          return (
            <button
              key={s.n}
              ref={(el) => { tabs.current[i] = el }}
              role="tab"
              id={`check-tab-${s.n}`}
              aria-selected={active}
              aria-controls="check-panel"
              tabIndex={active ? 0 : -1}
              onClick={() => setStage(s.n)}
              onKeyDown={(e) => onTabKey(e, i)}
              title={s.name}
              className={cn(
                "flex flex-col items-start gap-1 rounded-[16px] border px-3 py-2.5 text-left transition-colors duration-200",
                active ? "border-ink bg-ink text-white" : "border-line bg-raised text-ink hover:border-ink-3",
                count === 0 && !active && "opacity-45",
              )}
            >
              <span className="flex w-full items-center justify-between">
                <span className="font-mono text-[18px] leading-none font-semibold">{s.n}</span>
                {s.ai && <span className={cn("rounded-full px-1.5 font-mono text-[9px] leading-4", active ? "bg-accent text-white" : "bg-accent/10 text-accent")}>AI</span>}
              </span>
              <span className={cn("line-clamp-2 min-h-[2.5em] text-[11.5px] leading-tight", active ? "text-white/75" : "text-ink-3")}>{s.name}</span>
              <span className={cn("font-mono text-[10.5px]", active ? "text-white/60" : "text-ink-3")}>{count} case{count === 1 ? "" : "s"}</span>
            </button>
          )
        })}
      </div>

      <div id="check-panel" role="tabpanel" aria-labelledby={`check-tab-${stage}`} className="mt-6">
        {current && (
          <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
            <h3 className="text-h3">Step {current.n}: {current.name}</h3>
            <AiBadge ai={current.ai} />
            <p className="w-full max-w-2xl text-[15px] leading-relaxed text-ink-2">{current.what}</p>
          </div>
        )}
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.ul
            key={`${stage}-${filter}`}
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? { opacity: 0, transition: { duration: 0 } } : { opacity: 0 }}
            transition={{ duration: reduce ? 0 : 0.2 }}
            className="mt-5 grid gap-3 lg:grid-cols-2"
          >
            {here.map((c) => (
              <CaseCard key={c.code} c={c} focus={focusCode?.code === c.code ? focusCode.at : null} stageName={(n) => stages.find((s) => s.n === n)?.name} />
            ))}
            {here.length === 0 && catalogue && (
              <li className="rounded-card border border-dashed border-line p-6 text-[15px] text-ink-3 lg:col-span-2">
                No cases in this step match the filter.
              </li>
            )}
          </motion.ul>
        </AnimatePresence>
      </div>
    </Section>
  )
}

function CaseCard({ c, focus, stageName }: { c: CatalogueCase; focus: number | null; stageName: (n: number) => string | undefined }) {
  const ref = useRef<HTMLLIElement>(null)
  const reduce = useReducedMotion()
  const built = c.status === "Built"
  useEffect(() => {
    if (focus == null) return
    ref.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" })
    ref.current?.focus({ preventScroll: true })
  }, [focus, reduce])

  return (
    <li
      ref={ref}
      tabIndex={-1}
      id={`case-${c.code}`}
      className={cn(
        "flex flex-col gap-3 rounded-card border bg-raised p-5 outline-none",
        built ? "border-line" : "border-dashed border-ink-3/60 bg-raised/60",
        c.fraud && "border-reject/40",
        focus != null && "ring-2 ring-accent ring-offset-2 ring-offset-surface",
      )}
    >
      <div className="flex items-start gap-3">
        <CaseCodeChip c={c} />
        <h4 className="flex-1 text-[16px] leading-snug font-medium text-ink">{c.title}</h4>
        <BuiltBadge status={c.status} />
      </div>
      <p className="text-[14px] leading-relaxed text-ink-2">{c.trigger}</p>
      {c.note && <p className="border-l-[3px] border-line pl-3 text-[13px] leading-relaxed text-ink-2">{c.note}</p>}
      {c.runs_in && (
        <p className="font-mono text-[11.5px] text-ink-3">Checked during step {c.runs_in} ({stageName(c.runs_in)}), in the same AI reading.</p>
      )}
      {!c.finding && built && <p className="font-mono text-[11.5px] text-ink-3">The normal path: passes without writing a finding.</p>}
      <dl className="mt-auto grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-4 gap-y-2 border-t border-line pt-3">
        <dt className="label">Outcome</dt>
        <dd><OutcomeChip outcome={c.outcome} also={c.also} /></dd>
        <dt className="label">Alerts</dt>
        <dd className="flex items-center justify-between gap-3">
          <Alerted who={c.alerted} fraud={c.fraud} />
          {c.sample && built && <TryIt sample={c.sample} />}
        </dd>
      </dl>
    </li>
  )
}
