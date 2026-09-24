import { cn } from "@/lib/utils"
import { cells } from "./pixels"

// Two pixel brackets around a pixel "i": [i]. The dot of the i is the accent.
const MAP = [
  "##..o..##",
  "#.......#",
  "#...#...#",
  "#...#...#",
  "#...#...#",
  "#...#...#",
  "##.....##",
]
const INK = cells(MAP, "#")
const DOT = cells(MAP, "o")

export function MarkGlyph({ size = 22, className }: { size?: number; className?: string }) {
  return (
    <svg viewBox="0 0 9 7" width={(size * 9) / 7} height={size} className={className} aria-hidden shapeRendering="crispEdges">
      {INK.map(([x, y]) => (
        <rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} fill="var(--ink)" />
      ))}
      {DOT.map(([x, y]) => (
        <rect key={`d${x}-${y}`} x={x} y={y} width={1} height={1} fill="var(--accent)" />
      ))}
    </svg>
  )
}

export function Mark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <MarkGlyph />
      <span className="text-[17px] font-semibold tracking-[-0.02em] text-ink">InvoiceIQ</span>
    </span>
  )
}
