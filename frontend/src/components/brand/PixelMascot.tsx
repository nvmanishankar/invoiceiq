import { useId } from "react"

import { cn } from "@/lib/utils"
import { cells } from "./pixels"

export type MascotState = "idle" | "thinking" | "approved" | "hold" | "reject"

// Our own 12×12 character: an invoice sheet with a folded top-right corner,
// one antenna, a screen face, a ruled line for a belly and two feet.
// b = body, f = folded corner, a = antenna tip, s = antenna stem, t = feet
const BODY = [
  "...a........",
  "...s........",
  ".#######f...",
  ".########ff.",
  ".##########.",
  ".##########.",
  ".##########.",
  ".##########.",
  ".##########.",
  ".##########.",
  ".##########.",
  "..tt....tt..",
]
const SHEET = cells(BODY, "#")
const FOLD = cells(BODY, "f")

const MOUTHS: Record<MascotState, [number, number][]> = {
  idle: [[5, 8], [6, 8]],
  thinking: [[5, 8], [6, 8]],
  approved: [[3, 8], [8, 8], [4, 9], [5, 9], [6, 9], [7, 9]],
  hold: [[5, 8], [6, 8], [7, 8]],
  reject: [[3, 9], [4, 9], [5, 9], [6, 9], [7, 9], [8, 9]],
}

const LABEL: Record<MascotState, string> = {
  idle: "Iris is ready",
  thinking: "Iris is checking",
  approved: "Iris is happy: approved",
  hold: "Iris raises an eyebrow: on hold",
  reject: "Iris is stern: rejected",
}

function Px({ x, y, fill, className }: { x: number; y: number; fill: string; className?: string }) {
  return <rect x={x} y={y} width={1} height={1} fill={fill} className={className} />
}

export function PixelMascot({ state = "idle", size = 72, className }: { state?: MascotState; size?: number; className?: string }) {
  const id = useId().replace(/:/g, "")
  const body = `url(#m-grad-${id})`
  return (
    <svg
      viewBox="0 0 12 12"
      width={size}
      height={size}
      role="img"
      aria-label={LABEL[state]}
      shapeRendering="crispEdges"
      className={cn("shrink-0 overflow-visible", className)}
      data-state={state}
    >
      <defs>
        <linearGradient id={`m-grad-${id}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="var(--tx-violet)" />
          <stop offset="55%" stopColor="var(--tx-teal)" />
          <stop offset="100%" stopColor="var(--tx-sky)" />
        </linearGradient>
        <filter id={`m-noise-${id}`} x="0" y="0" width="100%" height="100%">
          <feTurbulence type="fractalNoise" baseFrequency="2.2" numOctaves="2" seed="7" result="n" />
          <feColorMatrix in="n" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.45 0" result="grain" />
          <feComposite in="grain" in2="SourceGraphic" operator="in" result="g" />
          <feMerge>
            <feMergeNode in="SourceGraphic" />
            <feMergeNode in="g" />
          </feMerge>
        </filter>
      </defs>

      <g filter={`url(#m-noise-${id})`}>
        {SHEET.map(([x, y]) => (
          <Px key={`${x}-${y}`} x={x} y={y} fill={body} />
        ))}
      </g>
      {FOLD.map(([x, y]) => (
        <Px key={`f${x}-${y}`} x={x} y={y} fill="#D9D3F7" />
      ))}
      <Px x={3} y={1} fill="var(--ink)" />
      <Px x={3} y={0} fill="var(--tx-pink)" className={state === "thinking" ? "mascot-pulse" : undefined} />
      {[[2, 11], [3, 11], [8, 11], [9, 11]].map(([x, y]) => (
        <Px key={`t${x}`} x={x} y={y} fill="var(--ink)" />
      ))}

      {/* eyes: white sockets, ink pupils */}
      <g className={state === "idle" ? "mascot-blink" : undefined}>
        {[[3, 6], [4, 6], [7, 6], [8, 6]].map(([x, y]) => (
          <Px key={`e${x}`} x={x} y={y} fill="#fff" />
        ))}
        <g className={state === "thinking" ? "mascot-scan" : undefined}>
          <Px x={state === "approved" ? 4 : 3} y={6} fill="var(--ink)" />
          <Px x={state === "approved" ? 8 : 7} y={6} fill="var(--ink)" />
        </g>
      </g>

      {/* brows */}
      {state === "hold" && <Px x={8} y={4} fill="var(--ink)" />}
      {state === "hold" && <Px x={3} y={5} fill="var(--ink)" />}
      {state === "reject" && (
        <>
          <Px x={3} y={5} fill="var(--ink)" />
          <Px x={4} y={5} fill="var(--ink)" />
          <Px x={7} y={5} fill="var(--ink)" />
          <Px x={8} y={5} fill="var(--ink)" />
        </>
      )}

      {MOUTHS[state].map(([x, y]) => (
        <Px key={`m${x}-${y}`} x={x} y={y} fill="var(--ink)" />
      ))}

      {/* ruled line on the belly */}
      {state !== "reject" && state !== "approved" &&
        [3, 4, 5, 6, 7, 8].map((x) => <Px key={`r${x}`} x={x} y={10} fill="rgba(255,255,255,0.55)" />)}
    </svg>
  )
}
