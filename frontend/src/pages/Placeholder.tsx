export function Placeholder({ title }: { title: string }) {
  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="mb-4 text-xl font-semibold tracking-tight">{title}</h1>
      <div className="rounded-xl border bg-card p-8 text-sm text-muted-foreground shadow-xs">
        Coming in a later phase.
      </div>
    </div>
  )
}
