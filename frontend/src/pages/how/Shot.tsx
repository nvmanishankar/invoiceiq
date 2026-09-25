import { useRef, type ReactNode } from "react"

/** A screenshot in a browser-style frame with a caption. Click to enlarge in a native <dialog>. */
export function Shot({ file, path, alt, caption, width, height }: {
  /** In frontend/public/how-it-works/. */
  file: string
  /** The address shown in the frame, e.g. "/review". */
  path: string
  alt: string
  caption: ReactNode
  width: number
  height: number
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const src = `/how-it-works/${file}`
  return (
    <figure className="flex flex-col gap-2.5">
      <button
        type="button"
        onClick={() => dialog.current?.showModal()}
        aria-label={`Enlarge screenshot: ${alt}`}
        className="group block w-full cursor-zoom-in overflow-hidden rounded-card border border-line bg-surface text-left transition-colors duration-200 hover:border-ink-3"
      >
        <span className="flex items-center gap-3 border-b border-line px-3.5 py-2.5" aria-hidden>
          <span className="flex gap-1.5">
            {[0, 1, 2].map((i) => <span key={i} className="size-2 rounded-full bg-line" />)}
          </span>
          <span className="truncate rounded-full bg-raised px-3 py-0.5 font-mono text-[11px] text-ink-3">{path}</span>
          <span className="ml-auto font-mono text-[11px] text-ink-3 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
            Enlarge
          </span>
        </span>
        <img src={src} alt={alt} width={width} height={height} loading="lazy" decoding="async" className="block h-auto w-full" />
      </button>
      <figcaption className="text-[13px] leading-relaxed text-ink-2">{caption}</figcaption>

      <dialog
        ref={dialog}
        aria-label={alt}
        onClick={(e) => { if (e.target === e.currentTarget) e.currentTarget.close() }}
        className="m-auto max-h-[94vh] max-w-[96vw] overflow-visible bg-transparent p-0 backdrop:bg-ink/75"
      >
        <div className="relative">
          <img src={src} alt="" width={width} height={height} className="block h-auto max-h-[90vh] w-auto max-w-[94vw] rounded-[10px] border border-line bg-raised" />
          <button
            type="button"
            autoFocus
            onClick={() => dialog.current?.close()}
            aria-label="Close"
            className="absolute -top-3 -right-3 flex size-9 items-center justify-center rounded-full bg-ink text-white shadow-float transition-colors duration-200 hover:bg-accent"
          >
            <svg viewBox="0 0 16 16" className="size-3.5" aria-hidden>
              <path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
            </svg>
          </button>
        </div>
      </dialog>
    </figure>
  )
}
