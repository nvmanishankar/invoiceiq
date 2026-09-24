import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

/** 6×36 ink bar, then the heading. Tops every content panel. */
export function SectionTitle({ children, aside, className, id }: { children: ReactNode; aside?: ReactNode; className?: string; id?: string }) {
  return (
    <div className={cn("flex items-center gap-4", className)}>
      <span aria-hidden className="h-9 w-1.5 shrink-0 rounded-full bg-ink" />
      <h2 id={id} className="text-h2">{children}</h2>
      {aside && <div className="ml-auto">{aside}</div>}
    </div>
  )
}
