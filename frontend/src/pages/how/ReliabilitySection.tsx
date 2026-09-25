import type { ReactNode } from "react"
import { Link } from "react-router-dom"

import { PillButton } from "@/components/ds/PillButton"
import type { HowFacts } from "@/types"
import { Card, Section } from "./shared"
import { SHOTS } from "./shots"
import { Shot } from "./Shot"

export function ReliabilitySection({ facts }: { facts: HowFacts | undefined }) {
  const rows: { when: string; then: ReactNode }[] = [
    {
      when: "The AI is unavailable",
      then: <>A file seen before uses its saved answer. Otherwise the main model is tried, then a backup. If neither answers, the invoice is held as "couldn't be read automatically" and goes to review, where a person enters the details and presses Confirm. Comparing item descriptions falls back to plain text matching, marked lower confidence.</>,
    },
    {
      when: "A check crashes",
      then: <>That step records a system error and the invoice is held for a person. The other checks still run and the decision is still made.</>,
    },
    {
      when: "An email fails",
      then: <>It's marked Failed in the Outbox, with a Retry button. A failed email never fails the invoice's run.</>,
    },
    {
      when: "The server restarts mid-run",
      then: <>On startup, any run still marked as checking is closed as a Hold with a note that the server restarted, so it reaches a person and its live view ends.</>,
    },
    {
      when: "Too many new invoices in a day",
      then: <>The AI reads up to {facts?.max_runs_per_day ?? "…"} new invoices a day. After that, new files are refused with a message to try tomorrow, and a vendor using their link is asked to try again tomorrow or reply by email. Samples, files read before and the invoices split out of one file don't count, and neither does the test suite: it runs on a scratch copy.</>,
    },
  ]
  return (
    <Section
      id="reliability"
      kicker="15 · Reliability"
      title="When things go wrong"
      lede="Nothing fails silently and no invoice is left stuck. When the system can't be sure, it holds the invoice for a person."
    >
      <dl className="overflow-hidden rounded-card border border-line bg-raised">
        {rows.map((r) => (
          <div key={r.when} className="grid gap-2 border-t border-line px-5 py-4 first:border-t-0 md:grid-cols-[220px_minmax(0,1fr)]">
            <dt className="text-[15px] font-medium text-ink">{r.when}</dt>
            <dd className="text-[14px] leading-relaxed text-ink-2">{r.then}</dd>
          </div>
        ))}
      </dl>

      <h3 className="mt-10 text-h3">Tested</h3>
      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <Card>
          <p className="num font-mono text-[28px] leading-none font-semibold tracking-tight text-ink">{facts?.tests.automated ?? "…"}</p>
          <p className="mt-2 text-[14px] leading-snug text-ink-2">automated tests in the code: every rule, the maths, the emails, who may do what, and this page's facts.</p>
        </Card>
        <Card>
          <p className="num font-mono text-[28px] leading-none font-semibold tracking-tight text-ink">{facts?.tests.samples ?? "…"}</p>
          <p className="mt-2 text-[14px] leading-snug text-ink-2">sample invoices, each with its expected decision and case codes. The Tests page runs them all on a scratch copy and compares.</p>
          <PillButton asChild variant="link" className="mt-3 text-[12px]">
            <Link to="/tests">Open the Tests page</Link>
          </PillButton>
        </Card>
      </div>
      <div className="mt-8">
        <Shot {...SHOTS.tests}
          alt={`The Tests page after running all ${facts?.tests.samples ?? 10} samples, each expected decision matched`}
          caption="The Tests page after Run all: each sample's expected and actual decision and codes. Live data is never touched." />
      </div>
    </Section>
  )
}
