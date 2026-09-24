import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

export const inputCls =
  "h-11 w-full rounded-input border border-line bg-raised px-4 text-[15px] text-ink placeholder:text-ink-3 transition-colors hover:border-ink-3 focus-visible:border-accent"

/** Outline for an input whose value has a problem. */
export const invalidCls = "border-reject/60 bg-reject-bg/40 hover:border-reject"

/** Label, the control, then either the problem (red) or a hint. `htmlFor` ties the label to the control. */
export function Field({ label, htmlFor, error, hint, className, children }: {
  label: ReactNode
  htmlFor?: string
  error?: string | null
  hint?: ReactNode
  className?: string
  children: ReactNode
}) {
  const msgId = htmlFor ? `${htmlFor}-msg` : undefined
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={htmlFor} className="label">{label}</label>
      {children}
      {error ? (
        <p id={msgId} role="alert" className="text-[13px] leading-snug text-reject">{error}</p>
      ) : hint ? (
        <p id={msgId} className="text-[13px] leading-snug text-ink-3">{hint}</p>
      ) : null}
    </div>
  )
}
