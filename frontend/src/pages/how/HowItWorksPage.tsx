import { useCallback, useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useReducedMotion } from "motion/react"

import { getCatalogue } from "@/api"
import { PixelMascot } from "@/components/brand/PixelMascot"
import { PillLink } from "@/components/ds/PillLink"
import { SpeechBubble } from "@/components/ds/SpeechBubble"
import { SplitContainer } from "@/components/ds/SplitContainer"
import { AiRulesSection } from "./AiRulesSection"
import { ChecksSection, type Filter } from "./ChecksSection"
import { DecisionSection } from "./DecisionSection"
import { GstSection } from "./GstSection"
import { JourneySection } from "./JourneySection"
import { PoSection } from "./PoSection"
import { ProblemSection } from "./ProblemSection"

const IRIS = "Here's everything I do, in plain words. Click anything."

const SECTIONS = [
  { id: "problem", label: "The problem" },
  { id: "journey", label: "The journey" },
  { id: "checks", label: "The 9 checks" },
  { id: "ai", label: "AI vs rules" },
  { id: "po", label: "Finding the PO" },
  { id: "decision", label: "The decision" },
  { id: "gst", label: "GST" },
]

/** The section nearest the top third of the screen. */
function useScrollSpy(ids: string[]) {
  const [active, setActive] = useState(ids[0])
  useEffect(() => {
    const seen = new Map<string, boolean>()
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) seen.set(e.target.id, e.isIntersecting)
      const first = ids.find((id) => seen.get(id))
      if (first) setActive(first)
    }, { rootMargin: "-25% 0px -65% 0px" })
    for (const id of ids) {
      const el = document.getElementById(id)
      if (el) io.observe(el)
    }
    return () => io.disconnect()
  }, [ids])
  return active
}

const SECTION_IDS = SECTIONS.map((s) => s.id)

export function HowItWorksPage() {
  const catalogue = useQuery({ queryKey: ["how", "catalogue"], queryFn: getCatalogue, staleTime: Infinity })
  const reduce = useReducedMotion()
  const active = useScrollSpy(SECTION_IDS)
  const [stage, setStage] = useState(1)
  const [filter, setFilter] = useState<Filter>("all")
  const [focusCode, setFocusCode] = useState<{ code: string; at: number } | null>(null)

  const jump = useCallback((id: string) => {
    const el = document.getElementById(id)
    if (!el) return
    el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" })
    if (el.tabIndex >= 0 || el.hasAttribute("tabindex")) el.focus({ preventScroll: true })
  }, [reduce])

  const showStage = useCallback((n: number) => {
    setStage(n)
    jump("checks")
  }, [jump])

  const showCase = useCallback((code: string) => {
    const c = catalogue.data?.cases.find((x) => x.code === code)
    if (!c) return
    setStage(c.stage)
    setFilter("all") // a filter could hide the case
    setFocusCode({ code, at: Date.now() })
  }, [catalogue.data])

  const counts = catalogue.data?.counts
  const rail = (
    <div className="flex flex-col gap-8 lg:sticky lg:top-24">
      <h1 className="text-h1">How it works</h1>
      <div className="flex flex-col gap-3">
        <PixelMascot state="idle" size={72} />
        <SpeechBubble text={IRIS} />
      </div>
      <p className="font-mono text-[13px] leading-relaxed text-ink-2" aria-live="polite">
        {counts ? <>{counts.total} cases mapped · <span className="text-ink">{counts.built} built today</span></>
          : catalogue.isError ? "Couldn't load the case list." : "Loading cases…"}
      </p>
      <nav aria-label="Sections" className="flex flex-col gap-2">
        {SECTIONS.map((s, i) => (
          <PillLink key={s.id} label={s.label} dot={i} active={active === s.id}
            aria-current={active === s.id ? "location" : undefined} onClick={() => jump(s.id)} />
        ))}
      </nav>
    </div>
  )

  return (
    <SplitContainer rail={rail}>
      <div className="flex flex-col gap-16">
        <ProblemSection onCase={showCase} onJump={jump} />
        <JourneySection onJump={jump} onStage={showStage} />
        <ChecksSection catalogue={catalogue.data} stage={stage} setStage={setStage} filter={filter} setFilter={setFilter} focusCode={focusCode} />
        <AiRulesSection catalogue={catalogue.data} />
        <PoSection />
        <DecisionSection catalogue={catalogue.data} onCase={showCase} />
        <GstSection catalogue={catalogue.data} onCase={showCase} />
      </div>
    </SplitContainer>
  )
}
