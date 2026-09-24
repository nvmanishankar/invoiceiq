import { useEffect, useState } from "react"

/** true while the top bar should be visible: near the top, or scrolling up. */
export function useHeadroom(offset = 80): boolean {
  const [visible, setVisible] = useState(true)
  useEffect(() => {
    let last = window.scrollY
    let ticking = false
    const onScroll = () => {
      if (ticking) return
      ticking = true
      requestAnimationFrame(() => {
        const y = window.scrollY
        if (y < offset) setVisible(true)
        else if (Math.abs(y - last) > 4) setVisible(y < last)
        last = y
        ticking = false
      })
    }
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [offset])
  return visible
}
