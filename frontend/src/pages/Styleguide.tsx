import { useState, type ReactNode } from "react"

import { DotMatrix } from "@/components/brand/DotMatrix"
import { Mark, MarkGlyph } from "@/components/brand/Mark"
import { PixelArrow } from "@/components/brand/PixelArrow"
import { PixelMascot, type MascotState } from "@/components/brand/PixelMascot"
import { AccordionItem } from "@/components/ds/Accordion"
import { DecisionStamp } from "@/components/ds/DecisionStamp"
import { FraudBanner } from "@/components/ds/FraudBanner"
import { PillButton } from "@/components/ds/PillButton"
import { PillLink } from "@/components/ds/PillLink"
import { SectionTitle } from "@/components/ds/SectionTitle"
import { SpeechBubble } from "@/components/ds/SpeechBubble"
import { SplitContainer } from "@/components/ds/SplitContainer"
import { CodeChip, StatusChip } from "@/components/ds/StatusChip"
import { GREETING } from "@/pages/process/narration"

const COLOURS: [string, string, string][] = [
  ["--canvas", "#F0F0EF", "Page background"],
  ["--surface", "#F5F5F4", "Large containers"],
  ["--raised", "#FFFFFF", "Pills, inputs, popovers"],
  ["--line", "#E2E2E0", "Borders and dividers"],
  ["--hover", "#EAEAE8", "Row hover, open accordion"],
  ["--bubble", "#E8E8E6", "Speech bubble"],
  ["--ink", "#0A0A0A", "Headings, primary buttons"],
  ["--ink-2", "#55555A", "Body text"],
  ["--ink-3", "#9A9A9F", "Captions"],
  ["--accent", "#2B5CF6", "Links, focus, dot-matrix"],
]
const DECISIONS: [string, string, string, string][] = [
  ["Approve", "--approve", "#12A150", "#E7F6EE"],
  ["Hold", "--hold", "#C77700", "#FDF3E1"],
  ["Reject / fraud", "--reject", "#D6333A", "#FCE9EA"],
]
const TEXTURE = ["--tx-violet", "--tx-teal", "--tx-pink", "--tx-lime", "--tx-sky", "--tx-amber"]
const MASCOT: MascotState[] = ["idle", "thinking", "approved", "hold", "reject"]
const LINES = [
  GREETING,
  "Reading the invoice… it's a scan, so I'm reading it visually.",
  "Finding the PO… The reference 'PO 105' was read as PO-2026-105.",
  "These bank or tax details don't match what we have on file. Stopping for Finance.",
]

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-6 border-b border-line pb-12 last:border-b-0 last:pb-0">
      <SectionTitle>{title}</SectionTitle>
      {children}
    </section>
  )
}

function Swatch({ token, hex, note, bg }: { token: string; hex: string; note: string; bg?: string }) {
  return (
    <div className="overflow-hidden rounded-card border border-line bg-raised">
      <div className="h-16" style={{ background: `var(${token})` }}>
        {bg && <div className="h-full w-1/2" style={{ background: bg }} />}
      </div>
      <div className="p-3">
        <p className="font-mono text-[12px] text-ink">{token}</p>
        <p className="font-mono text-[12px] text-ink-3">{hex}</p>
        <p className="mt-1 text-[13px] text-ink-2">{note}</p>
      </div>
    </div>
  )
}

export function Styleguide() {
  const [line, setLine] = useState(0)
  const [active, setActive] = useState(0)
  const rail = (
    <>
      <h1 className="text-h1">Styleguide</h1>
      <p className="leading-relaxed">
        Every token and component in InvoiceIQ. Styling only: none of this changes what the API does.
      </p>
      <div className="flex flex-col gap-2.5">
        {["Colour", "Type", "Shape", "Components", "Brand"].map((s, i) => (
          <PillLink key={s} label={s} dot={i} onClick={() => document.getElementById(`sg-${s}`)?.scrollIntoView({ behavior: "smooth" })} />
        ))}
      </div>
    </>
  )

  return (
    <SplitContainer rail={rail}>
      <div className="flex flex-col gap-12">
        <div id="sg-Colour">
          <Section title="Colour">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
              {COLOURS.map(([t, h, n]) => (
                <Swatch key={t} token={t} hex={h} note={n} />
              ))}
            </div>
            <p className="label">Decisions: colour on tint, always with a word</p>
            <div className="grid gap-3 md:grid-cols-3">
              {DECISIONS.map(([name, t, fg, bg]) => (
                <Swatch key={t} token={`${t}-bg`} bg={`var(${t})`} hex={`${fg} on ${bg}`} note={name} />
              ))}
            </div>
            <p className="label">Texture: mascot, dots and sample markers only, never data</p>
            <div className="flex flex-wrap gap-3">
              {TEXTURE.map((t) => (
                <span key={t} className="flex items-center gap-2 rounded-full border border-line bg-raised py-1.5 pr-3 pl-1.5">
                  <span className="texture size-6 rounded-full" style={{ ["--dot" as string]: `var(${t})` }} />
                  <span className="font-mono text-[12px] text-ink">{t}</span>
                </span>
              ))}
            </div>
          </Section>
        </div>

        <div id="sg-Type">
          <Section title="Type">
            <div className="flex flex-col gap-4">
              <p className="text-display font-semibold tracking-[-0.03em] text-ink">₹2,65,500</p>
              <p className="text-h1 text-ink">h1 40: Process</p>
              <p className="text-h2 text-ink">h2 28: How I'm checking this invoice</p>
              <p className="text-h3 text-ink">h3 20: Invoice vs PO-2026-109</p>
              <p className="text-base">Body 16 in Geist: Pay ₹2,65,500 to Deccan Office Interiors by 04 Nov 2026.</p>
              <p className="text-[14px]">Small 14: Compared against 3 earlier invoices.</p>
              <p className="label">Label 12 mono uppercase</p>
              <p className="font-mono text-[15px] text-ink">Geist Mono: the AI's voice, buttons, codes (6.5), run IDs.</p>
              <p className="num text-right text-[20px] text-ink">₹1,18,000.00 and 2,100 of 2,000</p>
            </div>
          </Section>
        </div>

        <div id="sg-Shape">
          <Section title="Shape">
            <div className="flex flex-wrap items-end gap-4">
              {[
                ["Container 28", "rounded-container", "h-24 w-40 bg-surface"],
                ["Card 20", "rounded-card", "h-20 w-32 bg-raised"],
                ["Input 14", "rounded-input", "h-12 w-28 bg-raised"],
                ["Pill", "rounded-full", "h-11 w-28 bg-raised"],
              ].map(([n, r, c]) => (
                <div key={n} className="flex flex-col gap-2">
                  <div className={`${r} ${c} border border-line`} />
                  <span className="font-mono text-[12px] text-ink-2">{n}</span>
                </div>
              ))}
              <div className="flex flex-col gap-2">
                <div className="h-20 w-40 rounded-card bg-raised shadow-float" />
                <span className="font-mono text-[12px] text-ink-2">Float shadow (popovers only)</span>
              </div>
            </div>
          </Section>
        </div>

        <div id="sg-Components">
          <Section title="Components">
            <p className="label">Buttons</p>
            <div className="flex flex-wrap items-center gap-4">
              <PillButton>Process invoice</PillButton>
              <PillButton variant="secondary">Process another</PillButton>
              <PillButton variant="link">View the run</PillButton>
              <PillButton disabled>Disabled</PillButton>
            </div>

            <p className="label">Pill links</p>
            <div className="grid max-w-md gap-2.5">
              {["Happy path", "No PO reference", "Bank changed"].map((l, i) => (
                <PillLink key={l} label={l} dot={i} active={active === i} onClick={() => setActive(i)}
                  hint={<p className="text-ink">Hover shows the sample's story here.</p>} />
              ))}
            </div>

            <p className="label">Agent speech bubble</p>
            <div className="flex max-w-lg items-start gap-4">
              <PixelMascot state="thinking" size={56} />
              <div className="flex-1">
                <SpeechBubble text={LINES[line]} />
                <PillButton variant="link" className="mt-3" onClick={() => setLine((l) => (l + 1) % LINES.length)}>
                  Next line
                </PillButton>
              </div>
            </div>

            <p className="label">Status chips and codes</p>
            <div className="flex flex-wrap items-center gap-2">
              <StatusChip status="pass" />
              <StatusChip status="warn" />
              <StatusChip status="fail" />
              <StatusChip status="info" />
              <CodeChip code="5.7" tone="pass" />
              <CodeChip code="6.5" tone="hold" />
              <CodeChip code="7.2" tone="reject" />
              <CodeChip code="9.5" />
            </div>

            <p className="label">Decision stamps</p>
            <div className="flex flex-wrap items-center gap-6">
              <DecisionStamp decision="Approve" />
              <DecisionStamp decision="Hold" />
              <DecisionStamp decision="Reject" />
              <DecisionStamp decision="Hold" size="sm" />
            </div>

            <p className="label">Fraud banner</p>
            <FraudBanner title="Finance must verify: bank account changed">
              The bank account on the invoice ends 7766; the one on file ends 4410. No email goes to the vendor.
            </FraudBanner>

            <p className="label">Evidence accordion</p>
            <div className="flex flex-col gap-1">
              <AccordionItem header={<span className="font-medium text-ink">Match PO</span>} defaultOpen>
                <p className="text-ink">PO-2026-117 fits the amount exactly, but it's for standing desks; the invoice is for mesh chairs.</p>
              </AccordionItem>
              <AccordionItem header={<span className="font-medium text-ink">Duplicates</span>}>
                <p className="text-ink">No duplicate among 4 earlier invoices.</p>
              </AccordionItem>
            </div>

            <p className="label">Dither accents</p>
            <div className="flex flex-wrap gap-4">
              <div className="relative h-24 w-48 overflow-hidden rounded-card border border-dashed border-ink-3 bg-raised">
                <div className="dither absolute inset-0 text-accent opacity-[0.15]" />
                <span className="relative grid h-full place-items-center text-[13px]">Dropzone hover</span>
              </div>
              {["text-approve", "text-hold", "text-reject"].map((c) => (
                <div key={c} className="relative h-24 w-40 overflow-hidden rounded-card border border-line bg-raised">
                  <div className={`dither-strip absolute inset-y-0 left-0 w-1.5 ${c}`} />
                  <span className="grid h-full place-items-center font-mono text-[12px]">Decision edge</span>
                </div>
              ))}
            </div>
          </Section>
        </div>

        <div id="sg-Brand">
          <Section title="Brand">
            <div className="flex flex-wrap items-center gap-8">
              <Mark />
              <MarkGlyph size={56} />
              <span className="flex items-center gap-3 text-ink">
                <PixelArrow size={10} /> <PixelArrow size={20} /> <PixelArrow size={30} className="text-accent" />
              </span>
            </div>
            <p className="label">Iris, five states</p>
            <div className="flex flex-wrap gap-8">
              {MASCOT.map((m) => (
                <figure key={m} className="flex flex-col items-center gap-2">
                  <PixelMascot state={m} size={96} />
                  <figcaption className="font-mono text-[12px] text-ink-2">{m}</figcaption>
                </figure>
              ))}
            </div>
            <p className="label">Dot-matrix wordmark: move the cursor over it</p>
            <div className="overflow-hidden rounded-card bg-accent px-6">
              <DotMatrix text="InvoiceIQ" color="#ffffff" height={220} />
            </div>
          </Section>
        </div>
      </div>
    </SplitContainer>
  )
}
