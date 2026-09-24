import { motion, useReducedMotion } from "motion/react"

import { cn } from "@/lib/utils"
import { DECISION_TONE, DECISION_WORD } from "@/lib/decision"
import type { Decision } from "@/types"


/** Big mono stamp that lands with a small overshoot. */
export function DecisionStamp({ decision, size = "lg", className }: { decision: Decision; size?: "sm" | "lg"; className?: string }) {
  const reduce = useReducedMotion()
  const tone = DECISION_TONE[decision]
  return (
    <motion.div
      key={decision}
      initial={reduce ? false : { scale: 0.9, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 18, mass: 0.8 }}
      className={cn(
        "inline-flex -rotate-2 items-center rounded-[10px] border-[2.5px] font-mono font-semibold tracking-[0.12em] uppercase",
        size === "lg" ? "px-4 py-1.5 text-[30px]" : "px-2.5 py-0.5 text-[15px]",
        tone.text,
        className,
      )}
      style={{ borderColor: tone.fg, backgroundColor: tone.bg }}
    >
      {DECISION_WORD[decision]}
    </motion.div>
  )
}
