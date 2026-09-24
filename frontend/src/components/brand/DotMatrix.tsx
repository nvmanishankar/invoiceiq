import { useEffect, useRef } from "react"
import { useReducedMotion } from "motion/react"

import { cn } from "@/lib/utils"

type Dot = { hx: number; hy: number; x: number; y: number; vx: number; vy: number }

const STEP = 10 // sample every 10px
const RADIUS = 3.5
const REPEL = 90
const SPRING = 0.08
const DAMPING = 0.82

/**
 * Text drawn as a grid of dots. Dots near the cursor are pushed away and spring back.
 * DPR-aware, pauses off-screen, static under reduced motion. No libraries.
 */
export function DotMatrix({
  text = "InvoiceIQ",
  color = "#ffffff",
  className,
  height = 200,
  fontWeight = 700,
}: {
  text?: string
  color?: string
  className?: string
  height?: number
  fontWeight?: number
}) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const reduce = useReducedMotion()

  useEffect(() => {
    const wrap = wrapRef.current
    const canvas = canvasRef.current
    if (!wrap || !canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    let dots: Dot[] = []
    let w = 0
    let h = 0
    let raf = 0
    let visible = true
    let settled = false
    const mouse = { x: -9999, y: -9999 }

    const build = () => {
      w = wrap.clientWidth
      h = wrap.clientHeight
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = Math.round(w * dpr)
      canvas.height = Math.round(h * dpr)
      canvas.style.width = `${w}px`
      canvas.style.height = `${h}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

      // Render the text once, offscreen, at CSS-pixel scale, then sample it.
      const off = document.createElement("canvas")
      off.width = w
      off.height = h
      const o = off.getContext("2d")
      if (!o) return
      let size = h * 0.78
      o.font = `${fontWeight} ${size}px "Geist Variable", system-ui, sans-serif`
      const measured = o.measureText(text).width
      if (measured > w * 0.92) size *= (w * 0.92) / measured
      o.font = `${fontWeight} ${size}px "Geist Variable", system-ui, sans-serif`
      o.textAlign = "center"
      o.textBaseline = "middle"
      o.fillStyle = "#000"
      o.fillText(text, w / 2, h / 2 + size * 0.04)
      const data = o.getImageData(0, 0, w, h).data
      dots = []
      for (let y = STEP / 2; y < h; y += STEP) {
        for (let x = STEP / 2; x < w; x += STEP) {
          const a = data[(Math.floor(y) * w + Math.floor(x)) * 4 + 3] / 255
          if (a > 0.5) dots.push({ hx: x, hy: y, x, y, vx: 0, vy: 0 })
        }
      }
      settled = false
      draw()
    }

    // Canvas can't read CSS variables; resolve "var(--x)" against the wrapper.
    const m = /^var\((--[\w-]+)\)$/.exec(color)
    const fill = m ? getComputedStyle(wrap).getPropertyValue(m[1]).trim() || "#000" : color

    const draw = () => {
      ctx.clearRect(0, 0, w, h)
      ctx.fillStyle = fill
      ctx.beginPath()
      for (const d of dots) {
        ctx.moveTo(d.x + RADIUS, d.y)
        ctx.arc(d.x, d.y, RADIUS, 0, Math.PI * 2)
      }
      ctx.fill()
    }

    const tick = () => {
      raf = 0
      if (!visible) return
      let moving = false
      for (const d of dots) {
        const dx = d.x - mouse.x
        const dy = d.y - mouse.y
        const dist = Math.hypot(dx, dy)
        if (dist < REPEL && dist > 0.01) {
          const force = (1 - dist / REPEL) * 6
          d.vx += (dx / dist) * force
          d.vy += (dy / dist) * force
        }
        d.vx = (d.vx + (d.hx - d.x) * SPRING) * DAMPING
        d.vy = (d.vy + (d.hy - d.y) * SPRING) * DAMPING
        d.x += d.vx
        d.y += d.vy
        if (Math.abs(d.vx) > 0.02 || Math.abs(d.vy) > 0.02 || Math.abs(d.hx - d.x) > 0.1 || Math.abs(d.hy - d.y) > 0.1) moving = true
      }
      draw()
      settled = !moving && mouse.x < -1000
      if (!settled) raf = requestAnimationFrame(tick)
    }

    const wake = () => {
      if (!raf && visible && !reduce) raf = requestAnimationFrame(tick)
    }

    const onMove = (e: PointerEvent) => {
      const r = canvas.getBoundingClientRect()
      mouse.x = e.clientX - r.left
      mouse.y = e.clientY - r.top
      wake()
    }
    const onLeave = () => {
      mouse.x = -9999
      mouse.y = -9999
      wake()
    }

    const ro = new ResizeObserver(() => build())
    ro.observe(wrap)
    const io = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting
      if (visible) wake()
    })
    io.observe(wrap)
    if (!reduce) {
      wrap.addEventListener("pointermove", onMove)
      wrap.addEventListener("pointerleave", onLeave)
    }
    // Geist may still be loading on first paint; redraw once it's in.
    document.fonts?.ready.then(() => build())

    return () => {
      ro.disconnect()
      io.disconnect()
      wrap.removeEventListener("pointermove", onMove)
      wrap.removeEventListener("pointerleave", onLeave)
      if (raf) cancelAnimationFrame(raf)
    }
  }, [text, color, fontWeight, reduce])

  return (
    <div ref={wrapRef} className={cn("relative w-full", className)} style={{ height }} aria-hidden>
      <canvas ref={canvasRef} className="absolute inset-0" />
    </div>
  )
}
