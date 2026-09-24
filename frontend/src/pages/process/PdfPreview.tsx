import { useState } from "react"

import { runFileUrl } from "@/api"
import { cn } from "@/lib/utils"

export function PdfPreview({ runId, fileName }: { runId: string; fileName: string | null }) {
  const [open, setOpen] = useState(false)
  return (
    <section className={cn("rounded-card border border-line transition-colors", open ? "bg-hover" : "bg-raised")}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-4 rounded-card px-6 py-4 text-left"
      >
        <span className="font-medium text-ink">Original PDF</span>
        <span className="truncate font-mono text-[13px] text-ink-3">{fileName}</span>
        <span aria-hidden className={cn("ml-auto font-mono text-ink-3 transition-transform duration-200", open && "rotate-45")}>+</span>
      </button>
      {open && (
        <div className="px-4 pb-4">
          <iframe title={`Original PDF: ${fileName ?? runId}`} src={runFileUrl(runId)} className="h-[760px] w-full rounded-input border border-line bg-raised" />
        </div>
      )}
    </section>
  )
}
