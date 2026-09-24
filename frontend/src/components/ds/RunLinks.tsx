import { Link } from "react-router-dom"

/** "Replaces RUN-…" / "Replaced by RUN-…" for runs linked by a corrected-invoice upload. */
export function RunLinks({ parent, child, to }: { parent?: string | null; child?: string | null; to: (runId: string) => string }) {
  if (!parent && !child) return null
  const link = (id: string) => (
    <Link to={to(id)} className="text-ink underline underline-offset-2 hover:text-accent">{id}</Link>
  )
  return (
    <p className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[13px] text-ink-2">
      {parent && <span>Replaces {link(parent)}</span>}
      {child && <span>Replaced by {link(child)}</span>}
    </p>
  )
}
