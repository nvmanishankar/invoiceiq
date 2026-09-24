import { SectionTitle } from "@/components/ds/SectionTitle"
import { CodeChip } from "@/components/ds/StatusChip"
import { cn } from "@/lib/utils"
import type { RunDetail } from "@/types"

const ORDER = ["Finance", "AP", "Procurement", "Vendor"]
const TONE = { pass: "pass", hold: "hold", reject: "reject", info: "info" } as const

/** Who would be told, and what. One card per audience. */
export function AlertGroups({ run }: { run: RunDetail }) {
  const groups = run.alert_groups
  const audiences = Object.keys(groups.by_audience).sort((a, b) => ORDER.indexOf(a) - ORDER.indexOf(b))
  const suppressed = groups.vendor_suppressed && !audiences.includes("Vendor")
  const alertFor = (aud: string) => run.alerts.find((a) => a.audience === aud)
  return (
    <section aria-labelledby="alerts-title">
      <SectionTitle id="alerts-title">Who gets told</SectionTitle>
      {!audiences.length && !suppressed && (
        <p className="mt-4 text-ink-2">Nobody needs to act. The invoice goes straight to payment.</p>
      )}
      <div className="mt-6 grid gap-3 empty:hidden md:grid-cols-2">
        {audiences.map((aud) => {
          const alert = alertFor(aud)
          return (
            <article key={aud} className="rounded-card border border-line bg-raised p-5">
              <header className="flex items-baseline justify-between gap-3">
                <h3 className="text-h3">{aud}</h3>
                {alert && (
                  <span className="font-mono text-[12px] text-ink-3">
                    {alert.status}, for {alert.intended_for}
                  </span>
                )}
              </header>
              <ul className="mt-3 flex flex-col gap-2">
                {groups.by_audience[aud].map((f, i) => (
                  <li key={`${f.code}-${i}`} className="flex gap-2.5 text-[14px] leading-relaxed text-ink">
                    <CodeChip code={f.label ?? f.code} tone={TONE[f.severity as keyof typeof TONE] ?? "neutral"} />
                    <span>{f.message}</span>
                  </li>
                ))}
              </ul>
            </article>
          )
        })}
        {suppressed && (
          <article className={cn("rounded-card border border-dashed border-reject/50 bg-reject-bg/50 p-5")}>
            <h3 className="text-h3">Vendor</h3>
            <p className="mt-2 font-mono text-[13px] font-medium text-reject">Vendor email suppressed</p>
            <p className="mt-1 text-[14px] leading-relaxed text-ink-2">
              There's a fraud finding on this invoice, so nothing goes to the vendor. Finance calls them on the number on file.
            </p>
          </article>
        )}
      </div>
    </section>
  )
}
