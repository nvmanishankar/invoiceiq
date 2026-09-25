import { useEffect, useState, type ReactNode } from "react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"

import { DecisionStamp } from "@/components/ds/DecisionStamp"
import { PillButton } from "@/components/ds/PillButton"
import { CodeChip } from "@/components/ds/StatusChip"
import { day } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { Catalogue, HowFacts, VendorLoop } from "@/types"
import { Section } from "./shared"
import { SHOTS } from "./shots"
import { Shot } from "./Shot"

const STEPS = [
  { title: "Held", sub: "Something the vendor must fix" },
  { title: "Autofilled email", sub: "Drafted from the findings" },
  { title: "Vendor opens the link", sub: "No login, only their invoice" },
  { title: "Uploads the corrected PDF", sub: "The vendor sees only “Received”" },
  { title: "Re-checked from step 1", sub: "A new run, all 9 checks" },
  { title: "Approved, linked", sub: "Replaces the original" },
]
const STEP_MS = 4200

export function VendorLoopSection({ loop, facts, catalogue, loopError }: {
  loop: VendorLoop | undefined
  facts: HowFacts | undefined
  catalogue: Catalogue | undefined
  loopError: boolean
}) {
  const reduce = useReducedMotion()
  const [step, setStep] = useState(0)
  const [playing, setPlaying] = useState(!reduce)
  useEffect(() => {
    if (!playing || reduce) return
    const t = setTimeout(() => setStep((s) => (s + 1) % STEPS.length), STEP_MS)
    return () => clearTimeout(t)
  }, [playing, step, reduce])
  const go = (i: number) => {
    setPlaying(false)
    setStep(i)
  }
  const days = facts?.token_days

  return (
    <Section
      id="vendor-loop"
      kicker="09 · The vendor loop"
      title="Getting a corrected invoice back"
      lede="When the problem is on the vendor's side, the fix comes from them. This is sample 04, which bills more than its PO has left, run through the real checks and email templates just now."
    >
      {loopError && <p role="alert" className="text-hold">Couldn't load the sample. Is the API running?</p>}
      <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
        <ol className="flex flex-col gap-1.5" aria-label="Steps of the vendor loop">
          {STEPS.map((s, i) => (
            <li key={s.title}>
              <button type="button" aria-current={step === i ? "step" : undefined} onClick={() => go(i)}
                className={cn(
                  "relative flex w-full items-start gap-3 overflow-hidden rounded-[14px] border px-3.5 py-2.5 text-left transition-colors duration-200",
                  step === i ? "border-ink bg-raised" : "border-transparent hover:bg-hover/60",
                )}>
                <span className={cn("mt-0.5 font-mono text-[12px]", step >= i ? "text-ink" : "text-ink-3")}>{i + 1}</span>
                <span className="flex flex-col">
                  <span className={cn("text-[15px]", step === i ? "font-medium text-ink" : "text-ink-2")}>{s.title}</span>
                  <span className="font-mono text-[11px] text-ink-3">{s.sub}</span>
                </span>
                {step === i && playing && !reduce && (
                  <motion.span key={`bar-${i}`} aria-hidden className="absolute bottom-0 left-0 h-[2px] bg-accent"
                    initial={{ width: "0%" }} animate={{ width: "100%" }} transition={{ duration: STEP_MS / 1000, ease: "linear" }} />
                )}
              </button>
            </li>
          ))}
          <li className="mt-2 flex items-center gap-3 px-1">
            <PillButton variant="secondary" arrow={false} className="h-9 px-4" onClick={() => setPlaying((p) => !p)}>
              {playing ? "Pause" : "Play"}
            </PillButton>
            <span className="font-mono text-[12px] text-ink-3">Step {step + 1} of {STEPS.length}</span>
          </li>
        </ol>

        <div className="min-h-[440px] rounded-card border border-line bg-raised p-5 md:p-6" aria-live="polite">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div key={step}
              initial={reduce ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
              exit={reduce ? undefined : { opacity: 0, y: -8 }} transition={{ duration: reduce ? 0 : 0.22 }}>
              {loop ? <Panel step={step} loop={loop} days={days} catalogue={catalogue} /> : <div className="h-80 animate-pulse rounded-card bg-hover" aria-busy />}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>

      <h3 className="mt-10 text-h3">The rules for the link</h3>
      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Rule big={days != null ? `${days} days` : "…"} small="The link works for this long from when the email is sent. After that the vendor is asked to reply with the PDF attached." />
        <Rule big="1 active" small="One live link per invoice. A newer email, like a reminder, replaces the old link, which stops working." />
        <Rule big="Used once" small="After the vendor uploads, the link is spent. Opening it again says a corrected invoice was already sent." />
        <Rule big="Reminders" small={`A reviewer can press Send reminder while the invoice waits: the last email goes again, with a fresh ${days ?? "…"}-day link. Nothing is sent on a timer.`} />
        <Rule big="Never on fraud" small="A vendor email is never built, sent, re-sent or opened on a fraud hold. The link also closes if the invoice is decided another way." tone="reject" />
        <Rule big="No decision shown" small="The vendor sees their invoice's number, date, total, PO and the issues for them. Never the decision, other findings or bank details." />
      </div>

      <div className="mt-8">
        <Shot {...SHOTS.respond}
          alt="The vendor's response page for sample 04: the invoice facts, what needs correcting, and an upload box"
          caption="What the vendor sees at the link: our name, their invoice, what needs correcting and an upload box. Nothing else about the run." />
      </div>
    </Section>
  )
}

function Rule({ big, small, tone }: { big: string; small: string; tone?: "reject" }) {
  return (
    <div className={cn("rounded-card border p-5", tone === "reject" ? "border-reject/30 bg-reject-bg" : "border-line bg-raised")}>
      <p className={cn("font-mono text-[20px] leading-none font-semibold tracking-tight", tone === "reject" ? "text-reject" : "text-ink")}>{big}</p>
      <p className="mt-2 text-[14px] leading-snug text-ink-2">{small}</p>
    </div>
  )
}

function Panel({ step, loop, days, catalogue }: { step: number; loop: VendorLoop; days: number | undefined; catalogue: Catalogue | undefined }) {
  const page = loop.response_page
  switch (step) {
    case 0:
      return (
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-4">
            <DecisionStamp decision={loop.decision} size="sm" />
            <p className="text-[15px] text-ink-2">Invoice {page?.invoice_no} from {page?.vendor_name}, {page?.total_display} against {page?.po_id}.</p>
          </div>
          <ul className="flex flex-col gap-2">
            {loop.findings.map((f) => (
              <li key={f.code} className="flex items-start gap-3 rounded-[14px] border border-line px-4 py-3">
                <CodeChip code={f.code} tone="hold" />
                <span className="text-[15px] leading-snug text-ink">{f.message}</span>
              </li>
            ))}
          </ul>
          <p className="text-[14px] leading-relaxed text-ink-2">
            Both findings are addressed to the vendor, so the review page opens on Send to vendor. With vendor auto-send
            on, the vendor was already emailed when it was held; otherwise that email waits in the Outbox. Either way, a
            newer email replaces its link.
          </p>
        </div>
      )
    case 1:
      return (
        <div className="flex flex-col gap-3">
          <p className="font-mono text-[12px] text-ink-3">For {loop.email.intended_for} · delivered to the owner's inbox in this demo</p>
          <div className="overflow-hidden rounded-[14px] border border-line">
            <p className="border-b border-line bg-surface px-4 py-2.5 text-[14px] font-medium text-ink">{loop.email.subject}</p>
            <pre className="max-h-[340px] overflow-auto px-4 py-3 font-mono text-[12.5px] leading-relaxed whitespace-pre-wrap text-ink">{loop.email.body}</pre>
          </div>
          <p className="text-[13px] text-ink-3">The real link replaces <span className="font-mono">&lt;link-created-when-sent&gt;</span> when the email is sent. Vendor subjects end with the run's Ref, so an emailed reply can be matched.</p>
        </div>
      )
    case 2:
      return page ? (
        <div className="flex flex-col gap-4">
          <p className="label">{page.company_name} · for {page.vendor_name}</p>
          <p className="text-h3">Please send a corrected invoice</p>
          <dl className="grid grid-cols-2 gap-3 rounded-[14px] border border-line p-4 sm:grid-cols-4">
            {([["Invoice", page.invoice_no], ["Date", day(page.invoice_date)], ["Total", page.total_display], ["PO", page.po_id]] as const).map(([k, v]) => (
              <div key={k}><dt className="label mb-1">{k}</dt><dd className="num font-mono text-[14px] text-ink">{v ?? "—"}</dd></div>
            ))}
          </dl>
          <div>
            <p className="label mb-2">What needs correcting</p>
            <ul className="flex list-disc flex-col gap-1.5 pl-5 text-[14px] text-ink">
              {page.issues.map((m) => <li key={m}>{m}</li>)}
            </ul>
          </div>
          <p className="font-mono text-[12px] text-ink-3">Link valid until {page.expires_on} ({days} days from sending).</p>
        </div>
      ) : null
    case 3:
      return (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col items-center justify-center gap-2 rounded-card border-2 border-dashed border-line px-6 py-10 text-center">
            <Doc />
            <p className="text-[15px] text-ink">ACME-2026-0417-corrected.pdf</p>
            <p className="font-mono text-[12px] text-ink-3">A PDF, same size limit as any upload</p>
          </div>
          <Say who="Vendor sees">Received, we're checking it</Say>
          <p className="text-[14px] leading-relaxed text-ink-2">
            AP gets an email saying the vendor sent a corrected invoice, with a link to follow it. The vendor can add a
            message (up to {page?.message_max.toLocaleString("en-IN") ?? "…"} characters); AP sees it in that email and
            in the invoice's history.
          </p>
        </div>
      )
    case 4:
      return <Recheck names={catalogue?.stages.map((s) => s.name) ?? []} />
    default:
      return (
        <div className="flex flex-col gap-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-[14px] border border-line p-4">
              <p className="label">Original · {loop.run_id}</p>
              <p className="mt-2 font-mono text-[13px] text-ink-2">Status: Superseded, replaced by a corrected invoice</p>
              <p className="mt-1 text-[14px] text-ink-2">Leaves the queue. Its decision stays Hold, and what it blocked still counts as money protected.</p>
            </div>
            <div className="rounded-[14px] border border-ink p-4">
              <p className="label">Corrected · new run</p>
              <div className="mt-2 flex items-center gap-3">
                <DecisionStamp decision="Approve" size="sm" />
                <span className="font-mono text-[13px] text-ink-2">Replaces {loop.run_id}</span>
              </div>
              <p className="mt-2 text-[14px] text-ink-2">Approved if it now passes every check. If not, it's held again and the loop repeats.</p>
            </div>
          </div>
          <p className="text-[14px] leading-relaxed text-ink-2">
            The two runs link to each other on the Process and Review pages. The dashboard counts the corrected run as the
            decision, so the invoice is never counted twice.
          </p>
        </div>
      )
  }
}

function Say({ who, children }: { who: string; children: ReactNode }) {
  return (
    <div className="rounded-[14px] bg-bubble px-4 py-3">
      <p className="label">{who}</p>
      <p className="mt-1 font-mono text-[13px] leading-relaxed text-ink">{children}</p>
    </div>
  )
}

function Doc() {
  return (
    <svg viewBox="0 0 24 24" className="size-8 text-ink-3" aria-hidden>
      <path d="M6 2h8l4 4v16H6z M14 2v4h4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  )
}

function Recheck({ names }: { names: string[] }) {
  const reduce = useReducedMotion()
  return (
    <div className="flex flex-col gap-4">
      <p className="text-[15px] text-ink-2">A corrected invoice is a new run, not an edit. It's read again and every check runs from the start. The duplicate check skips the invoice it replaces, so the correction isn't flagged as a copy of itself.</p>
      <ol className="grid gap-2 sm:grid-cols-3">
        {names.map((n, i) => (
          <motion.li key={n} className="flex items-center gap-2.5 rounded-full border border-line px-3.5 py-2"
            initial={reduce ? false : { opacity: 0.3 }} animate={{ opacity: 1 }}
            transition={{ delay: reduce ? 0 : 0.25 + i * 0.3, duration: reduce ? 0 : 0.2 }}>
            <motion.span aria-hidden className="size-2 rounded-full bg-approve"
              initial={reduce ? false : { scale: 0 }} animate={{ scale: 1 }}
              transition={{ delay: reduce ? 0 : 0.25 + i * 0.3, duration: reduce ? 0 : 0.2 }} />
            <span className="font-mono text-[12px] text-ink-3">{i + 1}</span>
            <span className="truncate text-[14px] text-ink">{n}</span>
          </motion.li>
        ))}
      </ol>
    </div>
  )
}
