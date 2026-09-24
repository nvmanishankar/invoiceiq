import { motion, useReducedMotion } from "motion/react"

import { AccordionItem } from "@/components/ds/Accordion"
import { SectionTitle } from "@/components/ds/SectionTitle"
import { StatusChip } from "@/components/ds/StatusChip"
import { ms } from "@/lib/format"
import { stageRow } from "@/lib/motion"
import type { Stage } from "@/types"
import { STAGE_NAMES, doing } from "./narration"
import { StageEvidence } from "./StageEvidence"

export function Timeline({ stages, running }: { stages: Stage[]; running: boolean }) {
  const reduce = useReducedMotion()
  const steps = stages.filter((s) => s.order <= STAGE_NAMES.length)
  const nextName = STAGE_NAMES[steps.length]
  const deciding = running && !nextName
  return (
    <section aria-labelledby="timeline-title">
      <SectionTitle id="timeline-title" aside={<span className="font-mono text-[13px] text-ink-3">{steps.length} of {STAGE_NAMES.length}</span>}>
        How I'm checking this invoice
      </SectionTitle>
      <motion.ol
        className="mt-6 flex flex-col gap-1"
        initial="hidden"
        animate="show"
        variants={{ show: { transition: { staggerChildren: reduce ? 0 : 0.06 } } }}
      >
        {steps.map((s) => (
          <motion.li key={s.order} variants={reduce ? undefined : stageRow} data-stage={s.name} data-status={s.status}>
            <AccordionItem
              headerClassName="py-4"
              header={
                <div className="grid w-full grid-cols-[64px_minmax(0,1fr)_auto] items-start gap-x-4 gap-y-1 md:grid-cols-[64px_200px_minmax(0,1fr)_auto_64px]">
                  <span className="label pt-1 md:col-start-1 md:row-start-1">Step {s.order}</span>
                  <span className="font-medium text-ink md:col-start-2 md:row-start-1">{s.name}</span>
                  <span className="col-span-2 row-start-2 text-[14px] leading-relaxed text-ink-2 md:col-span-1 md:col-start-3 md:row-start-1">{s.message}</span>
                  <StatusChip status={s.status} className="col-start-3 row-start-1 md:col-start-4" />
                  <span className="num hidden pt-0.5 text-right font-mono text-[12px] text-ink-3 md:col-start-5 md:row-start-1 md:block">{ms(s.duration_ms)}</span>
                </div>
              }
            >
              <StageEvidence stage={s} />
            </AccordionItem>
          </motion.li>
        ))}
        {running && (
          <li aria-live="polite" className="relative overflow-hidden rounded-card bg-hover/60 px-4 py-4">
            <div aria-hidden className="shimmer absolute inset-0" />
            <div className="relative grid grid-cols-[64px_minmax(0,1fr)] gap-4 md:grid-cols-[64px_200px_minmax(0,1fr)]">
              <span className="label pt-0.5">{deciding ? "Result" : `Step ${steps.length + 1}`}</span>
              <span className="font-medium text-ink">{deciding ? "Decision" : nextName}</span>
              <span className="hidden font-mono text-[13px] text-ink-3 md:block">{deciding ? "Weighing every finding…" : doing(nextName)}</span>
            </div>
          </li>
        )}
      </motion.ol>
    </section>
  )
}
