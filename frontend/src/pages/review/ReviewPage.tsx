import { useState } from "react"
import { Link, Navigate, useNavigate, useParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { ApiError, getReviewQueue, getRun, reviewRun, runFileUrl } from "@/api"
import { PixelMascot } from "@/components/brand/PixelMascot"
import { PillButton } from "@/components/ds/PillButton"
import { PillLink } from "@/components/ds/PillLink"
import { RunLinks } from "@/components/ds/RunLinks"
import { SectionTitle } from "@/components/ds/SectionTitle"
import { SpeechBubble } from "@/components/ds/SpeechBubble"
import { SplitContainer } from "@/components/ds/SplitContainer"
import { waitingFor } from "@/lib/format"
import { useRole } from "@/role"
import type { RunDetail } from "@/types"
import { DecisionCard } from "../process/DecisionCard"
import { FindingList } from "../process/StageEvidence"
import { Timeline } from "../process/Timeline"
import { changedFields, initialValues, type Values } from "./fields"
import { FieldsForm } from "./FieldsForm"
import { ReviewActions } from "./ReviewActions"
import { ReviewHistory } from "./ReviewHistory"

const REVIEWABLE = new Set(["needs_review", "waiting_on_vendor"])

export function ReviewPage() {
  const { runId } = useParams()
  const { role } = useRole()
  const navigate = useNavigate()
  const queue = useQuery({ queryKey: ["review-queue"], queryFn: getReviewQueue, refetchInterval: 15_000 })
  const runs = queue.data?.runs ?? []
  const parked = queue.data?.waiting ?? []

  // /review with a queue: open the invoice that has waited longest.
  if (!runId && runs.length) return <Navigate to={`/review/${encodeURIComponent(runs[0].run_id)}`} replace />

  const n = queue.data?.count ?? 0
  const bubble = queue.isLoading
    ? "Checking what's waiting for you…"
    : n === 0
      ? "Nothing is waiting. Every held invoice has been dealt with."
      : `${n} invoice${n === 1 ? " is" : "s are"} waiting for a person. You're reviewing as ${role}.`

  const rail = (
    <>
      <h1 className="text-h1">Review</h1>
      <div className="flex flex-col gap-3">
        <PixelMascot state={n ? "hold" : "approved"} size={72} />
        <SpeechBubble text={bubble} />
      </div>
      <nav aria-label="Held invoices" className="flex flex-col gap-2.5">
        <p className="label mb-1">Waiting for review</p>
        {queue.isError && <p className="text-[14px] text-hold">Couldn't load the queue. Is the API running?</p>}
        {runs.map((r, i) => (
          <PillLink
            key={r.run_id}
            dot={i}
            active={r.run_id === runId}
            label={`${r.vendor_name ?? r.file_name ?? r.run_id} · ${r.total_display ?? "no total"}`}
            onClick={() => navigate(`/review/${encodeURIComponent(r.run_id)}`)}
            hint={
              <>
                <p className="font-mono text-[12px] text-ink-3">{r.run_id} · {r.invoice_no ?? "no invoice number"}</p>
                {r.top_reason && <p className="mt-2 text-ink">{r.top_reason}</p>}
              </>
            }
          />
        ))}
      </nav>
      {parked.length > 0 && (
        <nav aria-label="Waiting on the vendor" className="flex flex-col gap-2.5">
          <p className="label mb-1">Waiting on the vendor</p>
          {parked.map((r, i) => (
            <PillLink
              key={r.run_id}
              dot={runs.length + i}
              active={r.run_id === runId}
              label={`${r.vendor_name ?? r.file_name ?? r.run_id} · ${waitingFor(r.waiting_since)}`}
              onClick={() => navigate(`/review/${encodeURIComponent(r.run_id)}`)}
              hint={
                <>
                  <p className="font-mono text-[12px] text-ink-3">{r.run_id} · {r.invoice_no ?? "no invoice number"}</p>
                  <p className="mt-2 text-ink">{waitingFor(r.waiting_since)} for a corrected invoice.</p>
                </>
              }
            />
          ))}
        </nav>
      )}
    </>
  )

  return (
    <SplitContainer rail={rail}>
      {runId ? (
        <RunReview key={runId} runId={runId} />
      ) : (
        <div>
          <SectionTitle>Nothing to review</SectionTitle>
          <p className="mt-4 max-w-prose text-ink-2">
            When an invoice is held, it lands here with the PDF, the fields that were read and what needs checking.
          </p>
          <PillButton asChild className="mt-6">
            <Link to="/process">Process an invoice</Link>
          </PillButton>
        </div>
      )}
    </SplitContainer>
  )
}

function RunReview({ runId }: { runId: string }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => getRun(runId) })

  if (run.isLoading) return <p className="text-ink-3">Loading {runId}…</p>
  if (run.error)
    return (
      <p role="alert" className="text-hold">
        {run.error instanceof ApiError && run.error.status === 404 ? `There's no run called ${runId}.` : run.error.message}
      </p>
    )
  if (!run.data) return null

  const done = (id: string) => {
    // The run changes now (or restarts, or a corrected upload replaces it), so drop the cached copies before the
    // Process page streams `id`.
    for (const key of new Set([id, runId])) {
      qc.removeQueries({ queryKey: ["run", key] })
      qc.removeQueries({ queryKey: ["vendor-email", key] })
    }
    qc.invalidateQueries({ queryKey: ["review-queue"] })
    qc.invalidateQueries({ queryKey: ["runs"] })
    qc.invalidateQueries({ queryKey: ["alerts"] })
    navigate(`/process?run=${encodeURIComponent(id)}`)
  }
  return <ReviewDetail run={run.data} onDone={done} />
}

function ReviewDetail({ run, onDone }: { run: RunDetail; onDone: (runId: string) => void }) {
  const [start] = useState<Values>(() => initialValues(run.extraction))
  const [values, setValues] = useState<Values>(start)
  const open = REVIEWABLE.has(run.status)
  const fraudFinding = run.findings.find((f) => f.fraud)
  const attention = run.findings.filter((f) => f.severity === "hold" || f.severity === "reject")

  return (
    <div className="flex flex-col gap-12">
      <div className="-mb-4 flex flex-wrap items-center gap-x-4 gap-y-2">
        <p className="min-w-0 truncate font-mono text-[13px] text-ink-2">
          {run.file_name ?? "No file"} <span className="text-ink-3">/ {run.run_id}</span>
        </p>
        <PillButton asChild variant="secondary" className="ml-auto">
          <Link to={`/process?run=${encodeURIComponent(run.run_id)}`}>Open in Process</Link>
        </PillButton>
        <RunLinks parent={run.parent_upload_id} child={run.replaced_by} to={(id) => `/review/${encodeURIComponent(id)}`} />
      </div>

      {!open && (
        <p role="status" className="rounded-card border border-line bg-raised p-5 text-ink">
          {run.status === "superseded"
            ? "A corrected invoice replaced this one, so there's nothing to review here. Its decision stays on record."
            : `This invoice is ${run.status.replace(/_/g, " ")}, so there's nothing to review.`}
        </p>
      )}
      {run.status === "waiting_on_vendor" && <WaitingOnVendor run={run} fraud={!!fraudFinding} />}

      {run.decision && <DecisionCard decision={run.decision} fraudFinding={fraudFinding} />}

      <section aria-labelledby="fields-title" className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="min-w-0">
          <p className="label mb-3">The invoice</p>
          {run.has_file ? (
            <iframe title={`Original PDF: ${run.file_name ?? run.run_id}`} src={runFileUrl(run.run_id)}
              className="h-[720px] w-full rounded-input border border-line bg-raised xl:sticky xl:top-24" />
          ) : (
            <p className="text-ink-3">There's no stored PDF for this run.</p>
          )}
        </div>
        <div className="min-w-0">
          <SectionTitle id="fields-title">What was read</SectionTitle>
          <p className="mt-3 mb-6 text-[14px] leading-relaxed text-ink-2">
            Check each value against the PDF. Amber means the reader wasn't sure or the value is missing. Leave a field
            blank if it isn't on the invoice; nothing is filled in by guessing.
          </p>
          <FieldsForm extraction={run.extraction} values={values} disabled={!open}
            onChange={(k, v) => setValues((s) => ({ ...s, [k]: v }))} />
        </div>
      </section>

      <section aria-labelledby="attention-title">
        <SectionTitle id="attention-title">What needs attention</SectionTitle>
        <div className="mt-6">
          <FindingList findings={attention} />
        </div>
      </section>

      {open && (
        <section aria-labelledby="actions-title">
          <SectionTitle id="actions-title">Decide</SectionTitle>
          <div className="mt-6">
            <ReviewActions run={run} changes={changedFields(start, values)} onDone={onDone} />
          </div>
        </section>
      )}

      {run.reviews.length > 0 && (
        <section aria-labelledby="history-title">
          <SectionTitle id="history-title">History</SectionTitle>
          <div className="mt-6">
            <ReviewHistory reviews={run.reviews} />
          </div>
        </section>
      )}

      <Timeline stages={run.stages} running={false} />
    </div>
  )
}

/** A run parked on the vendor: how long it has waited, and a reminder with a fresh response link. */
function WaitingOnVendor({ run, fraud }: { run: RunDetail; fraud: boolean }) {
  const { role } = useRole()
  const qc = useQueryClient()
  const remind = useMutation({
    mutationFn: () => reviewRun(run.run_id, { action: "send_reminder" }, role),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["run", run.run_id] })
      qc.invalidateQueries({ queryKey: ["alerts"] })
    },
  })
  return (
    <div role="status" className="flex flex-col gap-4 rounded-card border border-hold/40 bg-hold-bg p-5 text-ink">
      <p>
        <span className="font-medium">{waitingFor(run.waiting_since)}.</span> Waiting for the vendor to reply. Their
        corrected invoice arrives through the link in our email, or upload it below when it comes by email. You can
        still correct it, override or reject it here.
      </p>
      {!fraud && (
        <div className="flex flex-wrap items-center gap-3">
          <PillButton variant="secondary" disabled={remind.isPending} onClick={() => remind.mutate()}>
            {remind.isPending ? "Sending…" : "Send reminder"}
          </PillButton>
          <span className="text-[13px] text-ink-2">
            {remind.isSuccess ? "Reminder sent with a new link; the old link no longer works." : "Re-sends the last email with a new 7-day link."}
          </span>
        </div>
      )}
      {remind.error && <p role="alert" className="text-[14px] text-reject">{remind.error.message}</p>}
    </div>
  )
}
