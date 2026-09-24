import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Dialog } from "radix-ui"

import { getRun } from "@/api"
import { PillButton } from "@/components/ds/PillButton"
import { when } from "@/lib/format"
import { DecisionCard } from "../process/DecisionCard"
import { Timeline } from "../process/Timeline"

/** Side panel: the decision card and stage trail of one run. */
export function RunPanel({ runId, onClose }: { runId: string | null; onClose: () => void }) {
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => getRun(runId!), enabled: !!runId })
  const r = run.data
  return (
    <Dialog.Root open={!!runId} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink/20 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[760px] flex-col overflow-y-auto border-l border-line bg-surface shadow-float duration-250 data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right data-[state=open]:animate-in data-[state=open]:slide-in-from-right"
        >
          <header className="sticky top-0 z-10 flex flex-wrap items-center gap-x-4 gap-y-3 border-b border-line bg-surface/95 px-6 py-5 backdrop-blur-md md:px-10">
            <div className="min-w-0">
              <Dialog.Title className="truncate text-h3 font-medium tracking-[-0.02em] text-ink">
                {r?.invoice_no ?? r?.file_name ?? runId}
              </Dialog.Title>
              <p className="truncate font-mono text-[12px] text-ink-3">
                {runId}{r?.vendor_name ? ` · ${r.vendor_name}` : ""}{r?.created_at ? ` · ${when(r.created_at)}` : ""}
              </p>
            </div>
            <div className="ml-auto flex items-center gap-3">
              {runId && (
                <PillButton asChild variant="secondary">
                  <Link to={`/process?run=${encodeURIComponent(runId)}`}>Open in Process</Link>
                </PillButton>
              )}
              <Dialog.Close className="grid size-11 place-items-center rounded-full border border-line bg-raised font-mono text-ink hover:border-ink" aria-label="Close">
                ×
              </Dialog.Close>
            </div>
          </header>
          <div className="flex flex-col gap-10 px-6 py-8 md:px-10">
            {run.isLoading && <p className="text-ink-3">Loading {runId}…</p>}
            {run.isError && <p role="alert" className="text-hold">{run.error.message}</p>}
            {r && (
              <>
                {r.decision ? (
                  <DecisionCard decision={r.decision} fraudFinding={r.findings.find((f) => f.fraud)} />
                ) : (
                  <p className="rounded-card border border-line bg-raised p-5 text-ink">Still running. Open it in Process to watch it live.</p>
                )}
                <Timeline stages={r.stages} running={false} />
              </>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
