import { useEffect, useState } from "react"
import { useReducedMotion } from "motion/react"

/** Types `text` in at `msPerChar`; instant under reduced motion. */
export function useTypewriter(text: string, msPerChar = 30): { shown: string; done: boolean } {
  const reduce = useReducedMotion()
  const [state, setState] = useState({ text, count: reduce ? text.length : 0 })
  if (state.text !== text) setState({ text, count: reduce ? text.length : 0 })

  useEffect(() => {
    if (reduce) return
    const id = window.setInterval(() => {
      setState((s) => {
        if (s.count >= s.text.length) {
          window.clearInterval(id)
          return s
        }
        return { ...s, count: s.count + 1 }
      })
    }, msPerChar)
    return () => window.clearInterval(id)
  }, [text, msPerChar, reduce])

  const count = reduce ? text.length : state.count
  return { shown: text.slice(0, count), done: count >= text.length }
}
