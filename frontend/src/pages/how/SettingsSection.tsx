import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"

import { getSettings } from "@/api"
import { inr } from "@/lib/format"
import type { HowFacts } from "@/types"
import { Card, Section } from "./shared"

export function SettingsSection({ facts }: { facts: HowFacts | undefined }) {
  const s = useQuery({ queryKey: ["settings"], queryFn: getSettings }).data
  const items = [
    {
      title: "Company details", who: "Read-only",
      body: <>The buying company: {s ? <b className="font-medium text-ink">{s.company.name}</b> : "its name"}, GSTIN, state, address, currency and the AP, Procurement and Finance alert addresses. Set when InvoiceIQ is configured. The state decides CGST + SGST or IGST.</>,
    },
    {
      title: "Tolerance", who: "Finance only",
      body: <>How far an invoice may differ from its PO and still pass: a percentage from 0 to {facts?.max_tolerance_pct ?? "…"}%, capped at an amount up to {facts ? inr(facts.max_tolerance_cap_paise) : "…"}. {s && <>Now {s.tolerance_pct}% capped at {s.tolerance_cap_display}. </>}Each run reads it when it starts, so a change applies from the next invoice.</>,
    },
    {
      title: "Vendor auto-send", who: "Any role",
      body: <>On: a vendor email goes out as soon as an invoice is held for something they must fix. Off: it waits in the Outbox until someone presses Send. Internal alerts always go. The deployment can switch sending off entirely, which wins over this toggle.{s && <> Now {s.vendor_auto_send ? "on" : "off"}.</>}</>,
    },
    {
      title: "Reset demo data", who: "Any role · type RESET",
      body: <>Deletes every processed invoice, email and review, every PO and vendor added, and any settings changes, then restores the original POs, vendors and invoice history. It can't be undone.</>,
      danger: true,
    },
  ]
  return (
    <Section
      id="settings"
      kicker="14 · Settings"
      title="Settings"
      lede={<>Four things live in <Link to="/settings" className="text-ink underline underline-offset-2 hover:text-accent">Settings</Link>, under the menu at the top right.</>}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        {items.map((it) => (
          <Card key={it.title} className={it.danger ? "border-reject/30 bg-reject-bg/40" : undefined}>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="text-[17px] font-medium text-ink">{it.title}</h3>
              <span className="font-mono text-[11px] tracking-[0.06em] text-ink-3 uppercase">{it.who}</span>
            </div>
            <p className="mt-2 text-[14px] leading-relaxed text-ink-2">{it.body}</p>
          </Card>
        ))}
      </div>
    </Section>
  )
}
