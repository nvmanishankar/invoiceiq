import { useRef, useState } from "react"
import { useMutation } from "@tanstack/react-query"

import { ApiError, uploadCorrected } from "@/api"
import { PillButton } from "@/components/ds/PillButton"
import { useRole } from "@/role"

/** The vendor's corrected PDF becomes a new run, checked from step 1; this run is marked superseded. */
export function CorrectedUpload({ runId, onStarted }: { runId: string; onStarted: (newRunId: string) => void }) {
  const { role } = useRole()
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [warning, setWarning] = useState<string | null>(null)
  const upload = useMutation({
    mutationFn: (f: File) => uploadCorrected(runId, f, role),
    onSuccess: ({ run_id }) => onStarted(run_id),
  })

  const take = (files: FileList | null) => {
    const f = files?.[0]
    if (!f) return
    if (f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".pdf")) {
      setWarning(`${f.name} isn't a PDF.`)
      return
    }
    setWarning(null)
    setFile(f)
  }

  const error = upload.error
  return (
    <div className="flex flex-col gap-3">
      <p className="text-ink-2">
        The corrected invoice is checked in full from step 1, live on the Process page. This run is marked superseded
        and leaves the queue; its decision stays on record.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <PillButton type="button" variant="secondary" onClick={() => input.current?.click()} disabled={upload.isPending}>
          {file ? "Choose another PDF" : "Choose the corrected PDF"}
        </PillButton>
        {file && <span className="min-w-0 truncate font-mono text-[13px] text-ink-2">{file.name}</span>}
      </div>
      <input ref={input} type="file" accept="application/pdf,.pdf" className="sr-only" tabIndex={-1}
        aria-label="Corrected invoice PDF" onChange={(e) => { take(e.target.files); e.target.value = "" }} />
      {warning && <p role="alert" className="text-[14px] text-hold">{warning}</p>}
      {error && (
        <p role="alert" className="text-[14px] text-hold">
          {error instanceof ApiError && error.status === 429 ? `${error.message} The count resets at midnight.` : error.message}
        </p>
      )}
      <div>
        <PillButton disabled={!file || upload.isPending} onClick={() => file && upload.mutate(file)}>
          {upload.isPending ? "Uploading…" : "Upload and check"}
        </PillButton>
      </div>
    </div>
  )
}
