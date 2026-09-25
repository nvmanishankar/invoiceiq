import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

/** The page frame: one big surface, a 320px rail on the left, content on the right. */
export function SplitContainer({ rail, children, className }: { rail: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "grid overflow-clip rounded-container border border-line bg-surface lg:grid-cols-[320px_minmax(0,1fr)]",
        className,
      )}
    >
      <aside className="flex flex-col gap-8 border-b border-line p-8 lg:border-r lg:border-b-0 lg:p-10">{rail}</aside>
      <section className="min-w-0 p-6 md:p-10 xl:p-14">{children}</section>
    </div>
  )
}
