import { useState } from "react"
import { useSearchParams } from "react-router-dom"
import { useMutation, useQuery } from "@tanstack/react-query"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"

import { ApiError, createRun, getRun, getSamples } from "@/api"
import { DotMatrix } from "@/components/brand/DotMatrix"
import { PixelMascot, type MascotState } from "@/components/brand/PixelMascot"
import { PillButton } from "@/components/ds/PillButton"
import { PillLink } from "@/components/ds/PillLink"
import { SpeechBubble } from "@/components/ds/SpeechBubble"
import { SplitContainer } from "@/components/ds/SplitContainer"
import type { Decision } from "@/types"
import { AlertGroups } from "./AlertGroups"
import { CompareTable } from "./CompareTable"
import { DecisionCard } from "./DecisionCard"
import { Dropzone } from "./Dropzone"
import { narrate } from "./narration"
import { PdfPreview } from "./PdfPreview"
import { PoBalance } from "./PoBalance"
import { sampleName } from "./samples"
import { Timeline } from "./Timeline"
import { useRunStream } from "./useRunStream"

const MOOD: Record<Decision, MascotState> = { Approve: "approved", Hold: "hold", Reject: "reject" }

export function ProcessPage() {
  const [params, setParams] = useSearchParams()
  const runId = params.get("run")
  const [pending, setPending] = useState<{ label: string; runId: string | null } | null>(null)
  const reduce = useReducedMotion()

  const samples = useQuery({ queryKey: ["samples"], queryFn: getSamples, staleTime: Infinity })
  const start = useMutation({ mutationFn: createRun })

  const stream = useRunStream(runId)
  const settled = stream.done || stream.lost
  const detail = useQuery({
    queryKey: ["run", runId],
    queryFn: () => getRun(runId!),
    enabled: !!runId && settled,
  })
  const run = detail.data
  const stages = stream.stages.length ? stream.stages : (run?.stages ?? [])
  const decision = stream.decision ?? run?.decision ?? null
  const running = start.isPending || (!!runId && !settled)
  const mood: MascotState = running ? "thinking" : decision?.decision ? MOOD[decision.decision] : "idle"
  const activeFile = runId
    ? (run?.file_name ?? (pending?.runId === runId ? pending.label : null))
    : start.isPending ? (pending?.label ?? null) : null
  const fraudFinding = run?.findings.find((f) => f.fraud)
  const notFound = !!runId && stream.lost && detail.error instanceof ApiError && detail.error.status === 404

  const begin = (input: { file: File } | { sample_name: string }, label: string) => {
    setPending({ label, runId: null })
    start.reset()
    setParams({})
    start.mutate(input, {
      onSuccess: ({ run_id }) => {
        setPending({ label, runId: run_id })
        setParams({ run: run_id })
      },
    })
  }
  const reset = () => {
    setPending(null)
    start.reset()
    setParams({})
  }

  const rail = (
    <>
      <h1 className="text-h1">Process</h1>
      <div className="flex flex-col gap-3">
        <PixelMascot state={mood} size={72} />
        <SpeechBubble text={runId || start.isPending ? narrate(stages, decision, running) : narrate([], null, false)} />
      </div>
      <nav aria-label="Sample invoices" className="flex flex-col gap-2.5">
        <p className="label mb-1">Try a sample</p>
        {samples.isError && <p className="text-[14px] text-hold">Couldn't load the samples. Is the API running?</p>}
        {samples.data?.map((s, i) => (
          <PillLink
            key={s.file}
            label={sampleName(s.file)}
            dot={i}
            active={activeFile === s.file}
            disabled={running}
            data-sample={s.file}
            onClick={() => begin({ sample_name: s.file }, s.file)}
            hint={
              <>
                <p className="font-mono text-[12px] text-ink-3">{s.file}</p>
                <p className="mt-2 text-ink">{s.story}</p>
                <p className="mt-2 font-mono text-[12px] text-ink-2">Expect: {s.expected_decision}</p>
              </>
            }
          />
        ))}
      </nav>
    </>
  )

  const error = start.error
  return (
    <SplitContainer rail={rail}>
      {error && (
        <div role="alert" className="mb-8 rounded-card border border-hold/40 bg-hold-bg p-5">
          <p className="font-medium text-ink">
            {error instanceof ApiError && error.status === 429 ? "That's today's demo limit." : "That invoice didn't start."}
          </p>
          <p className="mt-1 text-[15px] leading-relaxed text-ink-2">
            {error.message}
            {error instanceof ApiError && error.status === 429 && " The count resets at midnight."}
          </p>
        </div>
      )}

      <AnimatePresence mode="wait" initial={false}>
        {!runId && !start.isPending ? (
          <motion.div
            key="idle"
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? undefined : { opacity: 0 }}
            transition={{ duration: reduce ? 0 : 0.25 }}
            className="flex flex-col gap-6"
          >
            <Dropzone onFile={(f) => begin({ file: f }, f.name)} />
            <div className="overflow-hidden rounded-card bg-accent px-6 pt-4 pb-2">
              <DotMatrix text="InvoiceIQ" color="#ffffff" height={220} />
              <p className="pb-3 font-mono text-[13px] text-white/75">
                Nine checks, one decision. Every rule is written in Python; the AI only reads the page.
              </p>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="run"
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: reduce ? 0 : 0.25 }}
            className="flex flex-col gap-12"
          >
            <div className="-mb-4 flex flex-wrap items-center gap-x-4 gap-y-2">
              <p className="min-w-0 truncate font-mono text-[13px] text-ink-2">
                {activeFile ?? "Starting…"}
                {runId && <span className="text-ink-3"> / {runId}</span>}
              </p>
              <PillButton variant="secondary" className="ml-auto" onClick={reset} disabled={running}>
                Process another
              </PillButton>
            </div>

            {notFound && <p role="alert" className="text-hold">There's no run called {runId}.</p>}
            {decision && <DecisionCard decision={decision} fraudFinding={fraudFinding} />}
            <Timeline stages={stages} running={running} />
            {run && run.comparison.length > 0 && <CompareTable rows={run.comparison} poId={run.po?.po_id ?? null} />}
            {run?.po && (
              <PoBalance po={run.po} invoicePaise={decision?.total_paise ?? null} approved={decision?.decision === "Approve"} />
            )}
            {run && <AlertGroups run={run} />}
            {run?.has_file && <PdfPreview runId={run.run_id} fileName={run.file_name} />}
          </motion.div>
        )}
      </AnimatePresence>
    </SplitContainer>
  )
}
