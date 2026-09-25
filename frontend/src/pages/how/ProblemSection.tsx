import { useState } from "react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"

import { CodeChip } from "@/components/ds/StatusChip"
import { cn } from "@/lib/utils"
import { Section } from "./shared"

const STEPS: { hand: string; iq: string }[] = [
  {
    hand: "A vendor emails an invoice PDF to the AP inbox.",
    iq: "You drop the PDF in. Typed or scanned, both work.",
  },
  {
    hand: "The clerk reads the vendor, invoice number, date, amounts and PO number.",
    iq: "The AI reads it once into a fixed form, and says which fields it isn't sure about.",
  },
  {
    hand: "They hunt for the matching purchase order in a spreadsheet.",
    iq: "Rules find the PO: from the printed number, or from what's on the invoice when there isn't one.",
  },
  {
    hand: "They check vendor, items, quantities, prices and tax by eye.",
    iq: "Every check runs, every time, in the same order, and each one leaves its evidence.",
  },
  {
    hand: "They decide to pay, query or reject, then chase the vendor by email.",
    iq: "Rules decide Approve, Hold or Reject, and email whoever owns each problem.",
  },
]

type Mistake = { title: string; cost: string; catch: string; codes: string[]; jump?: { id: string; label: string } }

const MISTAKES: Mistake[] = [
  {
    title: "Paying a duplicate",
    cost: "The same bill paid twice. Getting money back from a vendor is slow and awkward.",
    catch: "Compares every invoice with earlier ones from the same vendor, even if the number is rewritten or it's a new scan.",
    codes: ["7.1", "7.2", "7.3", "7.4"],
  },
  {
    title: "Over-billing",
    cost: "Paying more than was agreed on the purchase order. The budget quietly overspends.",
    catch: "Checks the total against what's left on the PO, and each price and quantity against what was ordered.",
    codes: ["6.3", "6.5", "6.6", "6.7"],
  },
  {
    title: "Bank fraud",
    cost: "A fake email changes the vendor's bank account. The money is usually gone for good.",
    catch: "Compares the bank account with the one on file. A change stops the invoice for Finance, and the vendor isn't emailed.",
    codes: ["4.7", "4.6"],
  },
  {
    title: "Wrong GST",
    cost: "The company can't reclaim the tax it paid, and the vendor must reissue the invoice.",
    catch: "Works out which GST applies from the two states, then checks the rate and the amount.",
    codes: ["8.3", "8.4", "8.5", "8.6"],
  },
  {
    title: "Slow follow-up",
    cost: "Problems sit in someone's inbox. Vendors get paid late and relationships sour.",
    catch: "Emails the owner of each problem as soon as the checks finish: one email per audience, listing every issue at once.",
    codes: [],
    jump: { id: "after-alerts", label: "See who gets told" },
  },
]

export function ProblemSection({ onCase, onJump }: { onCase: (code: string) => void; onJump: (id: string) => void }) {
  const [step, setStep] = useState(0)
  const [open, setOpen] = useState<number | null>(null)
  const reduce = useReducedMotion()

  return (
    <Section
      id="problem"
      kicker="01 · The problem"
      title="Before and after"
      lede="A company pays hundreds of vendor invoices a month. Someone in Accounts Payable (AP) checks each one against what was ordered before any money leaves. Pick a step to compare."
    >
      <div className="grid gap-3 md:grid-cols-2">
        <p className="label">Today, by hand</p>
        <p className="label hidden md:block">With InvoiceIQ</p>
      </div>
      <ol className="mt-3 flex flex-col gap-2">
        {STEPS.map((s, i) => {
          const active = step === i
          return (
            <li key={i}>
              <button
                type="button"
                aria-pressed={active}
                onClick={() => setStep(i)}
                className={cn(
                  "grid w-full gap-2 rounded-card border p-2 text-left transition-colors duration-200 md:grid-cols-2",
                  active ? "border-ink bg-raised" : "border-line bg-transparent hover:border-ink-3",
                )}
              >
                <span className="flex gap-3 rounded-[14px] px-3 py-2.5">
                  <span className="font-mono text-[13px] text-ink-3">{i + 1}</span>
                  <span className={cn("text-[15px] leading-snug", active ? "text-ink" : "text-ink-2")}>{s.hand}</span>
                </span>
                <span className={cn(
                  "flex gap-3 rounded-[14px] px-3 py-2.5 transition-colors duration-200",
                  active ? "bg-approve-bg" : "bg-hover/60",
                )}>
                  <span className="label mt-0.5 md:hidden">After</span>
                  <span className={cn("text-[15px] leading-snug", active ? "text-ink" : "text-ink-2")}>{s.iq}</span>
                </span>
              </button>
            </li>
          )
        })}
      </ol>

      <h3 className="mt-12 text-h3">What each mistake costs</h3>
      <p className="mt-2 text-[15px] text-ink-2">Open a card to see how it's caught. The codes jump to the check that catches it.</p>
      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {MISTAKES.map((m, i) => {
          const isOpen = open === i
          return (
            <div key={m.title} className={cn("rounded-card border bg-raised transition-colors duration-200", isOpen ? "border-ink" : "border-line")}>
              <button
                type="button"
                aria-expanded={isOpen}
                aria-controls={`mistake-${i}`}
                onClick={() => setOpen(isOpen ? null : i)}
                className="flex w-full items-start gap-3 rounded-card p-5 text-left"
              >
                <span className="flex-1">
                  <span className="block text-[17px] font-medium text-ink">{m.title}</span>
                  <span className="mt-1.5 block text-[14px] leading-relaxed text-ink-2">{m.cost}</span>
                </span>
                <span aria-hidden className={cn("font-mono text-ink-3 transition-transform duration-200", isOpen && "rotate-45")}>+</span>
              </button>
              <AnimatePresence initial={false}>
                {isOpen && (
                  <motion.div
                    id={`mistake-${i}`}
                    initial={reduce ? false : { height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={reduce ? { opacity: 0, transition: { duration: 0 } } : { height: 0, opacity: 0 }}
                    transition={{ duration: reduce ? 0 : 0.22 }}
                    className="overflow-hidden"
                  >
                    <div className="mx-5 mb-5 border-l-[3px] border-line pl-4">
                      <p className="text-[14px] leading-relaxed text-ink">{m.catch}</p>
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {m.codes.map((c) => (
                          <button key={c} type="button" onClick={() => onCase(c)} className="rounded-full" aria-label={`Show case ${c} in the 9 checks`}>
                            <CodeChip code={c} />
                          </button>
                        ))}
                        {m.jump && (
                          <button type="button" onClick={() => onJump(m.jump!.id)}
                            className="font-mono text-[12px] text-ink underline underline-offset-2 hover:text-accent">
                            {m.jump.label}
                          </button>
                        )}
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )
        })}
      </div>
    </Section>
  )
}
