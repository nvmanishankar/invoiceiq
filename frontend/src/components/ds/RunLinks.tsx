import { Link } from "react-router-dom"

import type { SplitOrigin } from "@/types"

const pagesText = (o: SplitOrigin) => {
  const p = o.pages
  const which = p.length > 1 ? `pages ${p[0]}–${p[p.length - 1]}` : `page ${p[0]}`
  return o.page_count ? `${which} of ${o.page_count}` : which
}

/** "Replaces RUN-…" / "Replaced by RUN-…" for runs linked by a corrected-invoice upload;
 * "Split from RUN-… (page n of m)" for one invoice of a multi-invoice PDF. */
export function RunLinks({ parent, child, splitFrom, to }: {
  parent?: string | null
  child?: string | null
  splitFrom?: SplitOrigin | null
  to: (runId: string) => string
}) {
  if (splitFrom) parent = null // its parent is the combined file, not a run it replaces
  if (!parent && !child && !splitFrom) return null
  const link = (id: string) => (
    <Link to={to(id)} className="text-ink underline underline-offset-2 hover:text-accent">{id}</Link>
  )
  return (
    <p className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[13px] text-ink-2">
      {splitFrom && <span>Split from {link(splitFrom.run_id)} ({pagesText(splitFrom)})</span>}
      {parent && <span>Replaces {link(parent)}</span>}
      {child && <span>Replaced by {link(child)}</span>}
    </p>
  )
}
