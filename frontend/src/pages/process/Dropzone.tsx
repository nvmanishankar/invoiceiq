import { useRef, useState } from "react"

import { PixelArrow } from "@/components/brand/PixelArrow"
import { cn } from "@/lib/utils"

export function Dropzone({ onFile, disabled }: { onFile: (f: File) => void; disabled?: boolean }) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const [warning, setWarning] = useState<string | null>(null)

  const take = (files: FileList | null) => {
    const f = files?.[0]
    if (!f) return
    if (f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".pdf")) {
      setWarning(`${f.name} isn't a PDF. Drop a PDF invoice.`)
      return
    }
    setWarning(null)
    onFile(f)
  }

  return (
    <div>
      <button
        type="button"
        disabled={disabled}
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setOver(true)
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          if (!disabled) take(e.dataTransfer.files)
        }}
        className={cn(
          "group relative flex min-h-[260px] w-full flex-col items-center justify-center gap-4 overflow-hidden rounded-card border border-dashed bg-raised p-10 text-center transition-colors duration-200 disabled:opacity-50",
          over ? "border-accent" : "border-ink-3 hover:border-ink",
        )}
      >
        <span aria-hidden className={cn("dither pointer-events-none absolute inset-0 text-accent transition-opacity duration-300", over ? "opacity-[0.15]" : "opacity-0 group-hover:opacity-[0.15]")} />
        <span className="relative grid size-12 place-items-center rounded-full bg-ink text-white transition-colors group-hover:bg-accent">
          <PixelArrow size={14} className="rotate-90" />
        </span>
        <span className="relative text-h3">Drop an invoice PDF</span>
        <span className="relative text-[14px] text-ink-2">or click to choose one. Up to 15 MB.</span>
      </button>
      <input ref={input} type="file" accept="application/pdf,.pdf" className="sr-only" tabIndex={-1} onChange={(e) => { take(e.target.files); e.target.value = "" }} />
      {warning && <p role="alert" className="mt-3 text-[14px] text-hold">{warning}</p>}
    </div>
  )
}
