import { cn } from "@/lib/utils"
import { cells } from "./pixels"

const ARROW = cells(["..#..", "...#.", "#####", "...#.", "..#.."])

/** Our 5×5 pixel arrow, drawn in currentColor. */
export function PixelArrow({ className, size = 10 }: { className?: string; size?: number }) {
  return (
    <svg viewBox="0 0 5 5" width={size} height={size} className={cn("shrink-0", className)} aria-hidden shapeRendering="crispEdges">
      {ARROW.map(([x, y]) => (
        <rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} fill="currentColor" />
      ))}
    </svg>
  )
}
