import type { ReactNode } from "react"
import { Link } from "react-router-dom"
import { motion, useReducedMotion } from "motion/react"

import { PillButton } from "@/components/ds/PillButton"
import { StatusChip } from "@/components/ds/StatusChip"
import { TextureDot } from "@/components/ds/TextureDot"
import { tour, TOUR_STEPS, useTour, type TourStep } from "@/hooks/useTour"
import { cn } from "@/lib/utils"

const COPY: Record<TourStep, { title: string; body: string }> = {
  pay: { title: "Pay a clean invoice", body: "Sample 01 matches its PO line for line, so it's approved with nobody touching it." },
  fraud: { title: "Catch a changed bank account", body: "Sample 06 asks to be paid into a new account. It's held as fraud and the vendor is not emailed." },
  overbill: { title: "Stop over-billing", body: "Sample 04 bills more than the PO has left. Open it in Review to see the autofilled Send to vendor and the vendor's upload link." },
  dashboard: { title: "See what it saved", body: "The Dashboard adds up the money protected by every hold and reject." },
  tests: { title: "Check every rule", body: "Tests runs all 10 samples on a scratch copy and compares each decision with the expected one." },
}

const SAMPLE: Partial<Record<TourStep, string>> = { pay: "01", fraud: "06", overbill: "04" }

/** "Start here" for someone opening the live link alone: five steps, each one click, ticked from the results. */
export function TourCard({ sampleFile, onRun, disabled }: {
  sampleFile: (prefix: string) => string | undefined
  onRun: (file: string) => void
  disabled: boolean
}) {
  const t = useTour()
  const reduce = useReducedMotion()
  const next = TOUR_STEPS.find((s) => !t.done.includes(s))

  const action = (step: TourStep): ReactNode => {
    const variant = step === next ? "primary" : "secondary"
    if (step === "overbill" && t.overbillRun && !t.done.includes("overbill")) {
      return (
        <PillButton asChild variant={variant}>
          <Link to={`/review/${encodeURIComponent(t.overbillRun)}`}>Open in Review</Link>
        </PillButton>
      )
    }
    const prefix = SAMPLE[step]
    if (prefix) {
      const file = sampleFile(prefix)
      return (
        <PillButton variant={variant} disabled={disabled || !file} onClick={() => file && onRun(file)}>
          Run sample {prefix}
        </PillButton>
      )
    }
    const [to, label] = step === "dashboard" ? ["/dashboard", "Open the Dashboard"] : ["/tests?run=all", "Run all samples"]
    return (
      <PillButton asChild variant={variant}>
        <Link to={to}>{label}</Link>
      </PillButton>
    )
  }

  return (
    <section aria-labelledby="tour-title" className="rounded-card border border-line bg-raised p-6">
      <header className="flex items-start gap-4">
        <div className="flex min-w-0 flex-col gap-1">
          <h2 id="tour-title" className="text-h3">Start here: 5 steps, about 3 minutes</h2>
          <p className="font-mono text-[13px] text-ink-3">{t.done.length} of 5 done</p>
        </div>
        <PillButton variant="link" arrow={false} className="ml-auto text-ink-2" onClick={tour.dismiss}>
          Hide
        </PillButton>
      </header>

      <ol className="mt-5 flex flex-col">
        {TOUR_STEPS.map((step, i) => {
          const done = t.done.includes(step)
          return (
            <li key={step} className="flex flex-wrap items-center gap-x-4 gap-y-3 border-t border-line py-4 sm:flex-nowrap">
              <span className="flex size-7 shrink-0 items-center justify-center">
                {done ? (
                  <motion.svg
                    viewBox="0 0 16 16" className="size-7 rounded-full bg-approve-bg p-1.5 text-approve" aria-hidden
                    initial={reduce ? false : { scale: 0.5, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
                    transition={{ duration: reduce ? 0 : 0.2 }}
                  >
                    <path d="M3 8.5l3.2 3L13 4.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </motion.svg>
                ) : (
                  <TextureDot index={i} size={14} />
                )}
              </span>
              <div className="min-w-0 flex-1 basis-60">
                <p className={cn("font-medium", done ? "text-ink-2" : "text-ink")}>
                  <span className="font-mono text-[13px] text-ink-3">{i + 1}. </span>
                  {COPY[step].title}
                  {done && <span className="sr-only"> (done)</span>}
                </p>
                <p className="mt-0.5 text-[14px] leading-snug text-ink-2">{COPY[step].body}</p>
              </div>
              <div className="ml-11 flex shrink-0 items-center gap-3 sm:ml-0">
                {done && <StatusChip status="pass" word="Done" />}
                {action(step)}
              </div>
            </li>
          )
        })}
      </ol>

      <p className="border-t border-line pt-4 text-[14px] leading-snug text-ink-2">
        Switch the role at the top (Procurement, AP clerk, Finance) to see who can do what.
      </p>
    </section>
  )
}
