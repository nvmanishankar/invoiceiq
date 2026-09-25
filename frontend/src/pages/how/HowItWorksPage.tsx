import { useCallback, useEffect, useRef, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useReducedMotion } from "motion/react"

import { getCatalogue, getHowFacts, getVendorLoop } from "@/api"
import { PixelMascot } from "@/components/brand/PixelMascot"
import { PillLink } from "@/components/ds/PillLink"
import { SpeechBubble } from "@/components/ds/SpeechBubble"
import { SplitContainer } from "@/components/ds/SplitContainer"
import { AiRulesSection } from "./AiRulesSection"
import { AlertsSection } from "./AlertsSection"
import { ChecksSection, type Filter } from "./ChecksSection"
import { DashboardSection } from "./DashboardSection"
import { DecisionSection } from "./DecisionSection"
import { GstSection } from "./GstSection"
import { JourneySection } from "./JourneySection"
import { NextSection } from "./NextSection"
import { PoSection } from "./PoSection"
import { ProblemSection } from "./ProblemSection"
import { PurchasingSection } from "./PurchasingSection"
import { ReliabilitySection } from "./ReliabilitySection"
import { ReviewSection } from "./ReviewSection"
import { RolesSection } from "./RolesSection"
import { SettingsSection } from "./SettingsSection"
import { VendorLoopSection } from "./VendorLoopSection"

const IRIS = "Here's everything I do, in plain words. Click anything."

const SECTIONS = [
  { id: "problem", label: "The problem" },
  { id: "journey", label: "The journey" },
  { id: "checks", label: "The 9 checks" },
  { id: "ai", label: "AI vs rules" },
  { id: "po", label: "Finding the PO" },
  { id: "decision", label: "The decision" },
  { id: "gst", label: "GST" },
  { id: "review", label: "Review" },
  { id: "vendor-loop", label: "The vendor loop" },
  { id: "purchasing", label: "POs and vendors" },
  { id: "roles", label: "Roles" },
  { id: "alerts", label: "Alerts" },
  { id: "dashboard", label: "Dashboard" },
  { id: "settings", label: "Settings" },
  { id: "reliability", label: "Reliability" },
  { id: "next", label: "What's next" },
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
  const facts = useQuery({ queryKey: ["how", "facts"], queryFn: getHowFacts, staleTime: Infinity })
  const loop = useQuery({ queryKey: ["how", "vendor-loop"], queryFn: getVendorLoop, staleTime: Infinity })
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

  // With 16 sections the rail is taller than the screen: it scrolls on its own, keeping the current section in view.
  const railRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const rail = railRef.current
    const pill = rail?.querySelector<HTMLElement>('[aria-current="location"]')
    if (!rail || !pill || rail.scrollHeight <= rail.clientHeight) return
    const r = rail.getBoundingClientRect()
    const b = pill.getBoundingClientRect()
    if (b.top < r.top) rail.scrollTop -= r.top - b.top + 12
    else if (b.bottom > r.bottom) rail.scrollTop += b.bottom - r.bottom + 12
  }, [active])

  const counts = catalogue.data?.counts
  const rail = (
    <div ref={railRef} className="flex flex-col gap-8 lg:sticky lg:top-24 lg:-mx-2 lg:max-h-[calc(100vh-8rem)] lg:overflow-y-auto lg:overscroll-contain lg:px-2 lg:pb-2">
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
        <ReviewSection catalogue={catalogue.data} facts={facts.data} loop={loop.data} onCase={showCase} />
        <VendorLoopSection loop={loop.data} facts={facts.data} catalogue={catalogue.data} loopError={loop.isError} />
        <PurchasingSection facts={facts.data} />
        <RolesSection facts={facts.data} />
        <AlertsSection catalogue={catalogue.data} loop={loop.data} onCase={showCase} />
        <DashboardSection facts={facts.data} loop={loop.data} />
        <SettingsSection facts={facts.data} />
        <ReliabilitySection facts={facts.data} />
        <NextSection />
      </div>
    </SplitContainer>
  )
}
