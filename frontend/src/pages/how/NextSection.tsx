import { TextureDot } from "@/components/ds/TextureDot"
import { Section } from "./shared"

const GROUPS: { title: string; note: string; items: { title: string; body: string }[] }[] = [
  {
    title: "Next",
    note: "The next things to build",
    items: [
      { title: "Investigator agent on held invoices",
        body: "For each held invoice, gather the evidence a reviewer would look for (the PO's history, earlier invoices, the vendor record) and write a short brief with a suggested action. It suggests; a person and the rules still decide." },
      { title: "Three-way match with goods received",
        body: "Check invoiced quantities against what was actually received, not only what was ordered. Goods receipts are already in the demo data but aren't checked yet." },
      { title: "Learning from reviewers",
        body: "When reviewers keep making the same correction, like a vendor's other spelling or the PO they pick, suggest it next time. Suggestions only: rules never change on their own." },
      { title: "Payment file",
        body: "Export approved invoices, with amounts, bank details on file and due dates, as a file the bank can take." },
    ],
  },
  {
    title: "Later",
    note: "Bigger pieces",
    items: [
      { title: "Invoices from the AP mailbox", body: "Pick up PDFs sent to the AP inbox, instead of uploading them by hand." },
      { title: "ERP connectors", body: "Read POs and vendors from, and post approved invoices to, systems like SAP and Tally." },
      { title: "More tax countries", body: "Tax rules are kept per country. India's GST is the one built today." },
      { title: "Real logins and approval limits", body: "People sign in instead of picking a role, and each person can approve up to an amount." },
    ],
  },
]

export function NextSection() {
  return (
    <Section
      id="next"
      kicker="16 · What's next"
      title="What's next"
      lede="None of this is built yet. It's the plan, in order."
    >
      <div className="flex flex-col gap-8">
        {GROUPS.map((g, gi) => (
          <div key={g.title}>
            <div className="flex items-baseline gap-3">
              <h3 className="text-h3">{g.title}</h3>
              <span className="font-mono text-[12px] text-ink-3">{g.note}</span>
            </div>
            <ul className="mt-4 grid gap-3 sm:grid-cols-2">
              {g.items.map((it, i) => (
                <li key={it.title} className="rounded-card border border-dashed border-ink-3/60 bg-raised p-5">
                  <div className="flex items-center gap-3">
                    <TextureDot index={gi * 4 + i} size={12} />
                    <p className="text-[16px] font-medium text-ink">{it.title}</p>
                  </div>
                  <p className="mt-2 text-[14px] leading-relaxed text-ink-2">{it.body}</p>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </Section>
  )
}
