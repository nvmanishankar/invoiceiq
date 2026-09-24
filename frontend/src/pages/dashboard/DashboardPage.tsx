import { useState, type ReactNode } from "react"
import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"

import { getStats } from "@/api"
import { PixelMascot } from "@/components/brand/PixelMascot"
import { PillButton } from "@/components/ds/PillButton"
import { PillLink } from "@/components/ds/PillLink"
import { SectionTitle } from "@/components/ds/SectionTitle"
import { SpeechBubble } from "@/components/ds/SpeechBubble"
import { SplitContainer } from "@/components/ds/SplitContainer"
import type { Stats } from "@/types"
import { DecisionsChart, ReasonsChart } from "./Charts"
import { HealthStrip, KpiCards } from "./KpiCards"
import { RunPanel } from "./RunPanel"
import { RunsTable } from "./RunsTable"

const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "decisions", label: "Decisions over time" },
  { id: "reasons", label: "Top hold reasons" },
  { id: "health", label: "Health" },
  { id: "runs", label: "Runs" },
] as const

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`

/** Iris's one-line summary of the day. */
function irisLine(s: Stats | undefined, loading: boolean): string {
  if (loading) return "Adding up today's invoices…"
  if (!s) return "I can't reach the numbers right now. Is the API running?"
  const t = s.today
  if (!s.kpis.processed) return "No invoices yet. Process one and I'll start counting."
  if (!t.processed)
    return `Nothing new today. So far I've checked ${plural(s.kpis.processed, "invoice")}; ${s.kpis.touchless} went through without a person.`
  const rest = [t.held && `${t.held} on hold`, t.rejected && `${t.rejected} rejected`].filter(Boolean).join(", ")
  return `${plural(t.processed, "invoice")} today, ${t.touchless} paid without a person${rest ? `. ${rest}.` : "."}`
}

function Section({ id, title, aside, children }: { id: string; title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-24">
      <SectionTitle id={`${id}-title`} aside={aside}>{title}</SectionTitle>
      <div className="mt-6">{children}</div>
    </section>
  )
}

export function DashboardPage() {
  const stats = useQuery({ queryKey: ["stats"], queryFn: getStats, refetchInterval: 15_000 })
  const [active, setActive] = useState<string>(SECTIONS[0].id)
  const [openRun, setOpenRun] = useState<string | null>(null)
  const s = stats.data
  const empty = !!s && s.kpis.processed === 0 && s.kpis.in_progress === 0

  const jump = (id: string) => {
    setActive(id)
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })
  }

  const rail = (
    <>
      <h1 className="text-h1">Dashboard</h1>
      <div className="flex flex-col gap-3">
        <PixelMascot state={s?.kpis.open_review ? "hold" : s?.kpis.processed ? "approved" : "idle"} size={72} />
        <SpeechBubble text={irisLine(s, stats.isLoading)} />
      </div>
      {!empty && (
        <nav aria-label="Dashboard sections" className="flex flex-col gap-2.5 lg:sticky lg:top-24">
          <p className="label mb-1">Jump to</p>
          {SECTIONS.map((sec, i) => (
            <PillLink key={sec.id} dot={i} label={sec.label} active={active === sec.id} onClick={() => jump(sec.id)} />
          ))}
        </nav>
      )}
    </>
  )

  return (
    <SplitContainer rail={rail}>
      {stats.isLoading && <p className="text-ink-3">Loading the numbers…</p>}
      {stats.isError && <p role="alert" className="text-hold">Couldn't load the dashboard. Is the API running?</p>}
      {empty && (
        <div>
          <SectionTitle>Nothing to count yet</SectionTitle>
          <p className="mt-4 max-w-prose text-ink-2">
            Once invoices go through InvoiceIQ, this page shows how many were paid without a person, how much money the
            checks protected and what most often holds invoices up. Try a sample to see it fill in.
          </p>
          <PillButton asChild className="mt-6">
            <Link to="/process">Process an invoice</Link>
          </PillButton>
        </div>
      )}
      {s && !empty && (
        <div className="flex flex-col gap-14">
          <Section id="overview" title="Overview">
            <KpiCards stats={s} />
          </Section>
          <Section id="decisions" title="Decisions over time"
            aside={<span className="font-mono text-[13px] text-ink-3">Last {s.series.decisions_per_day.length} days</span>}>
            <DecisionsChart data={s.series.decisions_per_day} />
          </Section>
          <Section id="reasons" title="Top hold reasons"
            aside={<span className="font-mono text-[13px] text-ink-3">Runs held or rejected, by finding</span>}>
            <ReasonsChart data={s.series.top_reasons} />
          </Section>
          <Section id="health" title="Health">
            <HealthStrip stats={s} />
          </Section>
          <Section id="runs" title="Runs">
            <RunsTable vendors={s.vendors} openId={openRun} onOpen={setOpenRun} />
          </Section>
        </div>
      )}
      <RunPanel runId={openRun} onClose={() => setOpenRun(null)} />
    </SplitContainer>
  )
}
