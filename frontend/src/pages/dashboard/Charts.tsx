import type { ReactNode } from "react"
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

import { DECISION_TONE, DECISION_WORD } from "@/lib/decision"
import type { Decision, Stats } from "@/types"
import { shortDay } from "./format"

type DayRow = Stats["series"]["decisions_per_day"][number]
type ReasonRow = Stats["series"]["top_reasons"][number]

// Bottom to top. Hold and Reject are close in hue, so Reject also carries a hatch and every segment a 2px gap.
const STACK: Decision[] = ["Approve", "Hold", "Reject"]
const HATCH_ID = "dash-reject-hatch"
const AXIS_TICK = { fill: "var(--ink-3)", fontSize: 12, fontFamily: "var(--font-mono)" }

function Swatch({ d }: { d: Decision }) {
  return (
    <svg aria-hidden width="12" height="12" className="shrink-0">
      <rect width="12" height="12" rx="3" fill={d === "Reject" ? `url(#${HATCH_ID})` : DECISION_TONE[d].fg} />
    </svg>
  )
}

function TooltipBox({ title, rows }: { title: string; rows: { key: string; mark?: ReactNode; label: string; value: string | number }[] }) {
  return (
    <div className="min-w-44 rounded-input border border-line bg-raised px-4 py-3 text-[13px] shadow-float">
      <p className="mb-2 font-mono text-[12px] text-ink-3">{title}</p>
      {rows.map((r) => (
        <p key={r.key} className="flex items-center gap-2 py-0.5 text-ink">
          {r.mark}
          <span>{r.label}</span>
          <span className="num ml-auto pl-4 font-medium">{r.value}</span>
        </p>
      ))}
    </div>
  )
}

/** A stacked segment: 4px rounded top only when it's the highest non-empty segment of its day. */
function Segment(props: { x?: number; y?: number; width?: number; height?: number; fill?: string; payload?: DayRow; dataKey?: string }) {
  const { x = 0, y = 0, width = 0, height = 0, fill, payload, dataKey } = props
  if (!payload || height <= 0) return null
  const idx = STACK.indexOf(dataKey as Decision)
  const isTop = STACK.slice(idx + 1).every((d) => !payload[d])
  const gap = 2 // surface gap below every segment except the baseline one
  const h = Math.max(0, height - (idx > 0 ? gap : 0))
  const r = isTop ? Math.min(4, h, width / 2) : 0
  const d = `M${x},${y + h} V${y + r} Q${x},${y} ${x + r},${y} H${x + width - r} Q${x + width},${y} ${x + width},${y + r} V${y + h} Z`
  return <path d={d} fill={fill} />
}

export function DecisionsChart({ data }: { data: DayRow[] }) {
  const totals = Object.fromEntries(STACK.map((d) => [d, data.reduce((s, r) => s + r[d], 0)])) as Record<Decision, number>
  return (
    <figure className="flex flex-col gap-4">
      {/* The hatch lives in its own SVG so swatches and bars can both point at it. */}
      <svg aria-hidden width="0" height="0" className="absolute">
        <defs>
          <pattern id={HATCH_ID} width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="5" height="5" fill={DECISION_TONE.Reject.fg} />
            <rect width="1.6" height="5" fill="#ffffff" opacity="0.55" />
          </pattern>
        </defs>
      </svg>
      <ul aria-label="Legend" className="flex flex-wrap gap-x-5 gap-y-2 text-[13px] text-ink-2">
        {STACK.map((d) => (
          <li key={d} className="flex items-center gap-2">
            <Swatch d={d} />
            {DECISION_WORD[d]} <span className="num text-ink-3">{totals[d]}</span>
          </li>
        ))}
      </ul>
      <div className="h-64" aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: -20 }} barCategoryGap="30%">
            <CartesianGrid vertical={false} stroke="var(--line)" />
            <XAxis dataKey="date" tickFormatter={shortDay} tick={AXIS_TICK} tickLine={false} axisLine={{ stroke: "var(--line)" }}
              interval="preserveStartEnd" minTickGap={16} />
            <YAxis allowDecimals={false} tick={AXIS_TICK} tickLine={false} axisLine={false} width={48} />
            <Tooltip
              cursor={{ fill: "var(--hover)", opacity: 0.6 }}
              content={({ active, payload, label }) =>
                active && payload?.length ? (
                  <TooltipBox
                    title={shortDay(String(label))}
                    rows={[...STACK].reverse().map((d) => ({ key: d, mark: <Swatch d={d} />, label: DECISION_WORD[d], value: (payload[0].payload as DayRow)[d] }))}
                  />
                ) : null
              }
            />
            {STACK.map((d) => (
              <Bar key={d} dataKey={d} stackId="d" maxBarSize={24} isAnimationActive={false}
                fill={d === "Reject" ? `url(#${HATCH_ID})` : DECISION_TONE[d].fg} shape={<Segment dataKey={d} />} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <table className="sr-only">
        <caption>Decisions per day</caption>
        <thead>
          <tr><th scope="col">Day</th>{STACK.map((d) => <th key={d} scope="col">{DECISION_WORD[d]}</th>)}</tr>
        </thead>
        <tbody>
          {data.map((r) => (
            <tr key={r.date}><th scope="row">{shortDay(r.date)}</th>{STACK.map((d) => <td key={d}>{r[d]}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}

const ROW_PX = 40

export function ReasonsChart({ data }: { data: ReasonRow[] }) {
  if (!data.length) return <p className="text-ink-2">Nothing has been held or rejected yet.</p>
  const rows = data.map((r) => ({ ...r, name: r.title }))
  return (
    <figure>
      <div style={{ height: rows.length * ROW_PX + 8 }} aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 40, bottom: 0, left: 0 }} barCategoryGap={12}>
            <XAxis type="number" hide allowDecimals={false} />
            <YAxis
              type="category"
              dataKey="name"
              width={260}
              tickLine={false}
              axisLine={false}
              tick={({ x, y, payload, index }) => (
                <g transform={`translate(${x},${y})`}>
                  <text x={-52} dy={4} textAnchor="end" fill="var(--ink)" fontSize={14}>{String(payload.value)}</text>
                  <text x={-12} dy={4} textAnchor="end" fill="var(--ink-3)" fontSize={11} fontFamily="var(--font-mono)">{rows[index]?.label}</text>
                </g>
              )}
            />
            <Tooltip
              cursor={{ fill: "var(--hover)", opacity: 0.6 }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const r = payload[0].payload as ReasonRow
                return (
                  <TooltipBox
                    title={`${r.label} · ${r.title}`}
                    rows={[
                      { key: "hold", label: "Held", value: r.hold },
                      { key: "reject", label: "Rejected", value: r.reject },
                    ].filter((x) => x.value)}
                  />
                )
              }}
            />
            <Bar dataKey="count" maxBarSize={20} radius={[0, 4, 4, 0]} isAnimationActive={false}>
              {rows.map((r, i) => <Cell key={r.code} fill={i === 0 ? "var(--accent)" : "var(--ink)"} />)}
              <LabelList dataKey="count" position="right" offset={8} fill="var(--ink-2)" fontSize={13} className="num" />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <table className="sr-only">
        <caption>Top hold and reject reasons</caption>
        <thead><tr><th scope="col">Reason</th><th scope="col">Code</th><th scope="col">Runs</th></tr></thead>
        <tbody>
          {data.map((r) => <tr key={r.code}><th scope="row">{r.title}</th><td>{r.label}</td><td>{r.count}</td></tr>)}
        </tbody>
      </table>
    </figure>
  )
}
