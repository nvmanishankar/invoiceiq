import { useState, type ReactNode } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"

import { getSamples, runTestSuite } from "@/api"
import { PixelMascot, type MascotState } from "@/components/brand/PixelMascot"
import { DataTable, type Column } from "@/components/ds/DataTable"
import { PillButton } from "@/components/ds/PillButton"
import { SectionTitle } from "@/components/ds/SectionTitle"
import { SpeechBubble } from "@/components/ds/SpeechBubble"
import { SplitContainer } from "@/components/ds/SplitContainer"
import { CodeChip, StatusChip } from "@/components/ds/StatusChip"
import { DECISION_WORD } from "@/lib/decision"
import { day, ms, when } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { Decision, StageStatus, SuiteResult } from "@/types"
import { sampleName } from "@/pages/process/samples"

const IRIS = "I'll run all 10 sample invoices on a scratch copy of the data. Nothing here touches your real runs or sends email."
const DECISION_CHIP: Record<Decision, StageStatus> = { Approve: "pass", Hold: "warn", Reject: "fail" }

/** A table row: a finished result, or a sample still waiting for one. */
type Row = { file: string; story: string | null; expected: Decision; codes: string[]; result: SuiteResult | null }

function DecisionChip({ decision }: { decision: Decision | null }) {
  return decision ? <StatusChip status={DECISION_CHIP[decision]} word={DECISION_WORD[decision]} /> : <span className="text-ink-3">—</span>
}

function Shimmer({ className }: { className?: string }) {
  return (
    <span aria-hidden className={cn("relative block h-6 overflow-hidden rounded-full bg-hover", className)}>
      <span className="shimmer absolute inset-0" />
    </span>
  )
}

export function TestsPage() {
  const [open, setOpen] = useState<string | null>(null)
  const samples = useQuery({ queryKey: ["samples"], queryFn: getSamples, staleTime: Infinity })
  const suite = useMutation({ mutationFn: runTestSuite, onMutate: () => setOpen(null) })
  const running = suite.isPending
  const run = running ? null : suite.data
  const allPassed = !!run && run.passed === run.total

  const rows: Row[] = run
    ? run.results.map((r) => ({ file: r.file, story: r.story, expected: r.expected_decision, codes: r.expected_codes, result: r }))
    : (samples.data ?? []).map((s) => ({ file: s.file, story: s.story, expected: s.expected_decision, codes: s.expected_codes, result: null }))

  const toggle = (file: string) => setOpen((f) => (f === file ? null : file))
  const pending = (cell: (r: SuiteResult) => ReactNode, width = "w-16") => (row: Row) =>
    row.result ? cell(row.result) : running ? <Shimmer className={width} /> : <span className="text-ink-3">—</span>

  const columns: Column<Row>[] = [
    {
      key: "sample",
      head: "Sample",
      cell: (r) => (
        <button type="button" disabled={!r.result} aria-expanded={open === r.file}
          onClick={(e) => { e.stopPropagation(); toggle(r.file) }}
          className="flex flex-col items-start rounded-sm text-left disabled:cursor-default">
          <span className="font-medium whitespace-nowrap text-ink">{sampleName(r.file)}</span>
          <span className="font-mono text-[12px] text-ink-3">{r.file.slice(0, 2)}</span>
        </button>
      ),
    },
    { key: "story", head: "Story", cell: (r) => <span className="block max-w-sm text-[13px] leading-snug text-ink-2">{r.story ?? "—"}</span> },
    { key: "expected", head: "Expected", cell: (r) => <DecisionChip decision={r.expected} /> },
    { key: "actual", head: "Actual", cell: pending((res) => <DecisionChip decision={res.actual_decision} />, "w-20") },
    {
      key: "codes",
      head: "Codes",
      cell: (r) => {
        const missing = new Set(r.result?.missing_codes ?? [])
        const extra = r.result ? r.result.actual_codes.filter((c) => !r.codes.includes(c)).length : 0
        return (
          <div className="flex flex-wrap items-center gap-1.5">
            {r.codes.map((c) => <CodeChip key={c} code={c} tone={missing.has(c) ? "reject" : "neutral"} />)}
            {extra > 0 && <span className="font-mono text-[11px] text-ink-3">+{extra} more</span>}
          </div>
        )
      },
    },
    {
      key: "result",
      head: "Result",
      cell: pending((res) => <StatusChip status={res.passed ? "pass" : "fail"} word={res.passed ? "Pass" : "Fail"} />),
    },
    {
      key: "time",
      head: "Time",
      align: "right",
      cell: pending((res) => <span className="font-mono text-[12px] text-ink-3">{ms(res.duration_ms)}</span>, "ml-auto w-12"),
    },
  ]

  const mood: MascotState = running ? "thinking" : run ? (allPassed ? "approved" : "reject") : "idle"
  const rail = (
    <>
      <h1 className="text-h1">Tests</h1>
      <div className="flex flex-col gap-3">
        <PixelMascot state={mood} size={72} />
        <SpeechBubble text={IRIS} />
      </div>
      <div className="flex flex-col items-start gap-3">
        <PillButton onClick={() => suite.mutate()} disabled={running}>{running ? "Running…" : "Run all samples"}</PillButton>
        {suite.error && <p role="alert" className="text-[14px] leading-snug text-reject">{suite.error.message}</p>}
      </div>
      {run && (
        <div role="status" className="flex flex-col gap-1">
          <p className={cn("num font-mono text-[44px] leading-none font-semibold tracking-tight", allPassed ? "text-approve" : "text-reject")}>
            {run.passed} / {run.total}
          </p>
          <p className="text-[15px] text-ink">passed</p>
          <p className="font-mono text-[13px] text-ink-3">in {ms(run.duration_ms)} · {when(run.ran_at)}</p>
        </div>
      )}
    </>
  )

  return (
    <SplitContainer rail={rail}>
      <SectionTitle aside={<span className="font-mono text-[13px] text-ink-3">{running ? "Running…" : run ? "Latest run" : "Not run yet"}</span>}>
        Sample invoices
      </SectionTitle>
      {samples.isError && !run && <p role="alert" className="mt-4 text-hold">Couldn't load the samples. Is the API running?</p>}
      <div className="mt-6" aria-busy={running}>
        <DataTable caption="Test suite results" columns={columns} rows={rows} rowKey={(r) => r.file}
          onRowClick={(r) => r.result && toggle(r.file)}
          rowClassName={(r) => cn(r.result && !r.result.passed && "bg-reject-bg/30", open === r.file && "bg-hover")}
          renderExpanded={(r) => (open === r.file && r.result ? <Trail result={r.result} /> : null)} />
      </div>
      <p className="mt-4 text-[13px] text-ink-3">Expected codes must be present; extra findings are allowed.</p>
    </SplitContainer>
  )
}

/** The stage trail of one sample, straight from the suite's response (no stored run). */
function Trail({ result: r }: { result: SuiteResult }) {
  const facts: [string, string | null, string | null][] = []
  if (r.expected_po_id) facts.push(["PO", r.expected_po_id, r.actual_po_id])
  if (r.expected_due_date) facts.push(["Due date", day(r.expected_due_date), day(r.actual_due_date)])
  return (
    <div className="flex flex-col gap-4 pt-2">
      {r.error && <p role="alert" className="text-[14px] text-reject">{r.error}</p>}
      {r.stages.length > 0 && (
        <ol className="flex flex-col divide-y divide-line rounded-card border border-line bg-raised">
          {r.stages.map((s, i) => (
            <li key={i} className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-x-4 gap-y-1 px-4 py-3 md:grid-cols-[180px_minmax(0,1fr)_auto]">
              <span className="font-medium text-ink">{s.name}</span>
              <span className="col-span-2 row-start-2 text-[14px] leading-relaxed text-ink-2 md:col-span-1 md:col-start-2 md:row-start-1">{s.message}</span>
              <StatusChip status={s.status} className="col-start-2 row-start-1 md:col-start-3" />
            </li>
          ))}
        </ol>
      )}
      <dl className="flex flex-wrap gap-x-8 gap-y-2 font-mono text-[12px] text-ink-3">
        {facts.map(([k, exp, act]) => (
          <div key={k} className="flex gap-2">
            <dt>{k}</dt>
            <dd className={cn(exp === act ? "text-ink" : "text-reject")}>{act ?? "—"}{exp !== act && ` (expected ${exp})`}</dd>
          </div>
        ))}
        <div className="flex gap-2"><dt>Found</dt><dd className="text-ink">{r.actual_codes.join(", ") || "—"}</dd></div>
        <div className="flex gap-2"><dt>LLM calls</dt><dd className={r.llm_calls ? "text-reject" : "text-ink"}>{r.llm_calls}</dd></div>
      </dl>
    </div>
  )
}
