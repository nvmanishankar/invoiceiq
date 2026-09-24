import { DecisionStamp } from "@/components/ds/DecisionStamp"
import { DECISION_TONE } from "@/lib/decision"
import { FraudBanner } from "@/components/ds/FraudBanner"
import { CodeChip } from "@/components/ds/StatusChip"
import { cn } from "@/lib/utils"
import type { DecisionInfo, Finding } from "@/types"
import { FRAUD_TITLE } from "./narration"

const TONE = { pass: "pass", hold: "hold", reject: "reject", info: "info" } as const

export function DecisionCard({ decision, fraudFinding }: { decision: DecisionInfo; fraudFinding?: Finding }) {
  if (!decision.decision) return null
  const tone = DECISION_TONE[decision.decision]
  return (
    <section aria-label="Decision" className="relative overflow-hidden rounded-card border border-line bg-raised">
      <div aria-hidden className={cn("dither-strip absolute inset-y-0 left-0 w-1.5", tone.text)} />
      <div className="flex flex-col gap-6 py-7 pr-7 pl-9 md:py-8 md:pr-10 md:pl-12">
        {decision.fraud && (
          <FraudBanner title={(fraudFinding && FRAUD_TITLE[fraudFinding.code]) ?? "Finance must verify before paying"}>
            {fraudFinding?.message ?? "A vendor detail doesn't match the master record."} No email goes to the vendor.
          </FraudBanner>
        )}
        <div className="flex flex-wrap items-start gap-x-8 gap-y-4">
          <DecisionStamp decision={decision.decision} />
          <p className="min-w-0 flex-1 basis-80 text-[24px] leading-snug font-medium tracking-[-0.02em] text-ink">
            {decision.headline}
          </p>
        </div>
        {decision.reasons.length > 0 && (
          <div>
            <p className="label mb-3">{decision.decision === "Approve" ? "Why it passes" : "Why"}</p>
            <ul className="flex flex-col gap-2.5">
              {decision.reasons.map((r, i) => (
                <li key={`${r.code}-${i}`} className="flex gap-3">
                  <CodeChip code={r.label ?? r.code} tone={TONE[r.severity] ?? "neutral"} />
                  <span className="leading-relaxed text-ink">{r.message}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  )
}
