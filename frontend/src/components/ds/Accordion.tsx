import { useId, useState, type ReactNode } from "react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"

import { cn } from "@/lib/utils"

/** Evidence / FAQ row. Open: tinted row, content indented behind a 3px bar. */
export function AccordionItem({
  header,
  children,
  defaultOpen = false,
  className,
  headerClassName,
}: {
  header: ReactNode
  children: ReactNode
  defaultOpen?: boolean
  className?: string
  headerClassName?: string
}) {
  const [open, setOpen] = useState(defaultOpen)
  const reduce = useReducedMotion()
  const id = useId()
  return (
    <div className={cn("rounded-card transition-colors duration-200", open && "bg-hover", className)}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
        className={cn("flex w-full items-center gap-4 rounded-card px-4 py-3.5 text-left", !open && "hover:bg-hover/60", headerClassName)}
      >
        {header}
        <span aria-hidden className={cn("ml-auto font-mono text-ink-3 transition-transform duration-200", open && "rotate-45")}>+</span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            id={id}
            initial={reduce ? false : { height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={reduce ? { opacity: 0, transition: { duration: 0 } } : { height: 0, opacity: 0 }}
            transition={{ duration: reduce ? 0 : 0.22, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div className="mx-4 mb-4 ml-6 border-l-[3px] border-line pl-5 text-[14px]">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
