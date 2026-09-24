import type { Transition, Variants } from "motion/react"

export const EASE_OUT: Transition["ease"] = [0.16, 1, 0.3, 1]

export const pageEnter: Variants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.25, ease: EASE_OUT } },
}

export const stageRow: Variants = {
  hidden: { opacity: 0, y: 12 },
  show: (i: number = 0) => ({ opacity: 1, y: 0, transition: { duration: 0.22, ease: EASE_OUT, delay: i * 0.06 } }),
}

/** Motion off: every transition becomes instant. */
export const instant: Transition = { duration: 0 }
