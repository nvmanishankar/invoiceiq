import type { KeyboardEvent } from "react"
import { useReducedMotion } from "motion/react"

import { PixelArrow } from "@/components/brand/PixelArrow"
import { Section } from "./shared"

type Node = { key: string; label: string; sub: string; x: number; y: number; go: () => void }

const W = 150
const H = 60
const ROW1 = 70
const ROW2 = 210
// The dot's route: along the top row, down to Review, back along the bottom row, up into the checks again.
const ROUTE = `M ${95 + W / 2} ${ROW1} H 845 V ${ROW2} H 335 V ${ROW1}`

export function JourneySection({ onJump, onStage }: { onJump: (id: string) => void; onStage: (n: number) => void }) {
  const reduce = useReducedMotion()
  const nodes: Node[] = [
    { key: "upload", label: "Upload", sub: "Drop in a PDF", x: 95, y: ROW1, go: () => onStage(1) },
    { key: "checks", label: "9 checks", sub: "Read, match, verify", x: 335, y: ROW1, go: () => onJump("checks") },
    { key: "decision", label: "Decision", sub: "Approve · Hold · Reject", x: 590, y: ROW1, go: () => onJump("decision") },
    { key: "alerts", label: "Alerts", sub: "The right person", x: 845, y: ROW1, go: () => onJump("after-alerts") },
    { key: "review", label: "Review", sub: "A person decides", x: 845, y: ROW2, go: () => onJump("after-review") },
    { key: "vendor", label: "Vendor fix", sub: "Corrected invoice", x: 590, y: ROW2, go: () => onJump("after-vendor") },
    { key: "recheck", label: "Re-check", sub: "All 9 checks again", x: 335, y: ROW2, go: () => onJump("after-recheck") },
  ]
  const onKey = (e: KeyboardEvent, go: () => void) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault()
      go()
    }
  }

  return (
    <Section
      id="journey"
      kicker="02 · The journey"
      title="The journey at a glance"
      lede="Every invoice takes the same route. Most stop at the decision. Held ones loop through a person, and sometimes the vendor, until they're right. Click any step."
    >
      <div className="hidden rounded-card border border-line bg-raised p-4 md:block">
        <svg viewBox="0 0 940 280" className="w-full" role="group" aria-label="The invoice journey">
          <defs>
            <marker id="journey-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 0 L10 5 L0 10 z" fill="var(--ink-3)" />
            </marker>
          </defs>
          {/* edges */}
          <g stroke="var(--ink-3)" strokeWidth="1.5" fill="none" markerEnd="url(#journey-arrow)">
            <line x1={95 + W / 2} y1={ROW1} x2={335 - W / 2 - 4} y2={ROW1} />
            <line x1={335 + W / 2} y1={ROW1} x2={590 - W / 2 - 4} y2={ROW1} />
            <line x1={590 + W / 2} y1={ROW1} x2={845 - W / 2 - 4} y2={ROW1} />
            <line x1={845} y1={ROW1 + H / 2} x2={845} y2={ROW2 - H / 2 - 4} />
            <line x1={845 - W / 2} y1={ROW2} x2={590 + W / 2 + 4} y2={ROW2} />
            <line x1={590 - W / 2} y1={ROW2} x2={335 + W / 2 + 4} y2={ROW2} />
            <line x1={335} y1={ROW2 - H / 2} x2={335} y2={ROW1 + H / 2 + 4} strokeDasharray="4 4" />
          </g>
          <text x={595} y={ROW1 + 52} textAnchor="middle" className="fill-ink-3 font-mono text-[11px]">approved: done</text>
          <text x={855} y={(ROW1 + ROW2) / 2 + 4} className="fill-ink-3 font-mono text-[11px]">held</text>
          <text x={345} y={(ROW1 + ROW2) / 2 + 4} className="fill-ink-3 font-mono text-[11px]">new run</text>

          {nodes.map((n) => (
            <g
              key={n.key}
              role="button"
              tabIndex={0}
              aria-label={`${n.label}: ${n.sub}. Jump to this part.`}
              onClick={n.go}
              onKeyDown={(e) => onKey(e, n.go)}
              className="group cursor-pointer outline-none"
            >
              <rect x={n.x - W / 2 - 4} y={n.y - H / 2 - 4} width={W + 8} height={H + 8} rx={34}
                className="fill-none stroke-transparent stroke-2 group-focus-visible:stroke-accent" />
              <rect x={n.x - W / 2} y={n.y - H / 2} width={W} height={H} rx={30}
                className={
                  n.key === "checks"
                    ? "fill-ink transition-colors duration-200 group-hover:fill-accent"
                    : "fill-raised stroke-line transition-colors duration-200 group-hover:stroke-ink"
                }
                strokeWidth={1} />
              <text x={n.x} y={n.y - 3} textAnchor="middle"
                className={n.key === "checks" ? "fill-white text-[15px] font-medium" : "fill-ink text-[15px] font-medium"}>
                {n.label}
              </text>
              <text x={n.x} y={n.y + 15} textAnchor="middle"
                className={n.key === "checks" ? "fill-white/70 font-mono text-[10.5px]" : "fill-ink-3 font-mono text-[10.5px]"}>
                {n.sub}
              </text>
            </g>
          ))}

          {/* the travelling dot: an invoice on its way */}
          <circle r={6} fill="var(--accent)" stroke="var(--raised)" strokeWidth={2} cx={reduce ? 95 + W / 2 + 18 : 0} cy={reduce ? ROW1 : 0}
            pointerEvents="none">
            {!reduce && <animateMotion dur="9s" repeatCount="indefinite" path={ROUTE} rotate="0" />}
          </circle>
        </svg>
      </div>

      {/* narrow screens: the same steps as a list */}
      <ol className="flex flex-col gap-2 md:hidden">
        {nodes.map((n, i) => (
          <li key={n.key}>
            <button type="button" onClick={n.go}
              className="flex h-14 w-full items-center gap-3 rounded-full border border-line bg-raised px-5 text-left hover:border-ink">
              <span className="font-mono text-[12px] text-ink-3">{i + 1}</span>
              <span className="text-[15px] text-ink">{n.label}</span>
              <span className="truncate font-mono text-[11px] text-ink-3">{n.sub}</span>
              <PixelArrow size={9} className="ml-auto text-ink" />
            </button>
          </li>
        ))}
      </ol>
    </Section>
  )
}
