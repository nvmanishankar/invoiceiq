import { useState, type ReactNode } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { ApiError, getSettings, resetDemo, updateSettings } from "@/api"
import { Field, inputCls, invalidCls } from "@/components/ds/Field"
import { PillButton } from "@/components/ds/PillButton"
import { PillLink } from "@/components/ds/PillLink"
import { SectionTitle } from "@/components/ds/SectionTitle"
import { SplitContainer } from "@/components/ds/SplitContainer"
import { inr } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { AppSettings, SettingsInput } from "@/types"

const SECTIONS = [
  { id: "company", label: "Company" },
  { id: "tolerance", label: "Tolerance" },
  { id: "emails", label: "Emails" },
  { id: "demo", label: "Demo data" },
]

export function SettingsPage() {
  const settings = useQuery({ queryKey: ["settings"], queryFn: getSettings })

  const rail = (
    <>
      <h1 className="text-h1">Settings</h1>
      <p className="text-[15px] leading-relaxed text-ink-2">
        Changes apply from the next invoice: each run reads these settings when it starts.
      </p>
      <nav aria-label="Settings sections" className="flex flex-col gap-2.5">
        <p className="label mb-1">Jump to</p>
        {SECTIONS.map((s, i) => (
          <PillLink key={s.id} dot={i + 2} label={s.label}
            onClick={() => document.getElementById(s.id)?.scrollIntoView({ behavior: "smooth", block: "start" })} />
        ))}
      </nav>
    </>
  )

  return (
    <SplitContainer rail={rail}>
      {settings.isError && <p role="alert" className="text-hold">Couldn't load the settings. Is the API running?</p>}
      {settings.data && (
        <div className="flex flex-col gap-14">
          <Company s={settings.data} />
          <Tolerance s={settings.data} />
          <Emails s={settings.data} />
          <DemoData />
        </div>
      )}
    </SplitContainer>
  )
}

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-24">
      <SectionTitle id={`${id}-title`}>{title}</SectionTitle>
      <div className="mt-6">{children}</div>
    </section>
  )
}

function Company({ s }: { s: AppSettings }) {
  const c = s.company
  const rows: [string, string, boolean?][] = [
    ["Name", c.name],
    ["GSTIN", c.gstin ?? "—", true],
    ["State", c.state ?? "—"],
    ["Country and currency", `${c.country === "IN" ? "India" : c.country} · ${c.currency}`],
    ["Address", c.address ?? "—"],
    ["Alert addresses", `AP ${c.ap_email} · Procurement ${c.procurement_email} · Finance ${c.finance_email}`],
  ]
  return (
    <Section id="company" title="Company">
      <dl className="grid gap-x-8 gap-y-4 rounded-card border border-line bg-raised p-6 sm:grid-cols-[180px_minmax(0,1fr)]">
        {rows.map(([k, v, mono]) => (
          <div key={k} className="contents">
            <dt className="text-[13px] text-ink-3 sm:pt-0.5">{k}</dt>
            <dd className={cn("text-[15px] break-words text-ink", mono && "font-mono")}>{v}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-[13px] text-ink-3">Read-only here: the buying company is set when InvoiceIQ is configured.</p>
    </Section>
  )
}

/** min(pct of the amount, cap), as the server's allowed_diff. */
function allowed(amountPaise: number, pct: number, capPaise: number) {
  return Math.min(Math.round((amountPaise * pct) / 100), capPaise)
}

function Tolerance({ s }: { s: AppSettings }) {
  const qc = useQueryClient()
  const [pct, setPct] = useState(String(s.tolerance_pct))
  const [cap, setCap] = useState(String(s.tolerance_cap_paise / 100))
  // New settings from the server (a save, or a demo reset): show those values.
  const [shownFor, setShownFor] = useState(s)
  if (shownFor !== s) {
    setShownFor(s)
    setPct(String(s.tolerance_pct))
    setCap(String(s.tolerance_cap_paise / 100))
  }
  const save = useMutation({
    mutationFn: (body: SettingsInput) => updateSettings(body),
    onSuccess: (data) => qc.setQueryData(["settings"], data),
  })
  const errors = save.error instanceof ApiError ? save.error.errors : {}
  const pctN = Number(pct)
  const capN = Number(cap.replace(/[,₹\s]/g, ""))
  const localPct = pct.trim() === "" || !Number.isFinite(pctN) || pctN < 0 || pctN > 10 ? "Tolerance is a percentage from 0 to 10." : null
  const localCap = cap.trim() === "" || !Number.isFinite(capN) || capN < 0 || capN > 100000 ? "The cap is an amount from ₹0 to ₹1,00,000." : null
  const dirty = pctN !== s.tolerance_pct || Math.round(capN * 100) !== s.tolerance_cap_paise
  const ok = !localPct && !localCap

  return (
    <Section id="tolerance" title="Tolerance">
      <p className="max-w-prose text-[15px] leading-relaxed text-ink-2">
        How far an invoice may differ from its PO (total, remaining balance, unit price) and still pass: a percentage
        of the amount, capped at a fixed sum.
      </p>
      <form className="mt-6 grid max-w-2xl gap-5 sm:grid-cols-2" noValidate
        onSubmit={(e) => { e.preventDefault(); if (ok) save.mutate({ tolerance_pct: pctN, tolerance_cap: capN }) }}>
        <Field label="Percentage" htmlFor="tol-pct" error={localPct ?? errors.tolerance_pct}>
          <div className="relative">
            <input id="tol-pct" inputMode="decimal" value={pct} onChange={(e) => setPct(e.target.value)}
              className={cn(inputCls, "num pr-9 text-right", (localPct || errors.tolerance_pct) && invalidCls)} />
            <span aria-hidden className="pointer-events-none absolute top-1/2 right-4 -translate-y-1/2 text-ink-3">%</span>
          </div>
        </Field>
        <Field label="Cap" htmlFor="tol-cap" error={localCap ?? errors.tolerance_cap}>
          <div className="relative">
            <span aria-hidden className="pointer-events-none absolute top-1/2 left-4 -translate-y-1/2 text-ink-3">₹</span>
            <input id="tol-cap" inputMode="decimal" value={cap} onChange={(e) => setCap(e.target.value)}
              className={cn(inputCls, "num pl-8 text-right", (localCap || errors.tolerance_cap) && invalidCls)} />
          </div>
        </Field>
        {ok && (
          <p className="text-[14px] leading-relaxed text-ink-2 sm:col-span-2">
            On ₹1,00,000 an invoice may be off by up to <span className="num text-ink">{inr(allowed(10_000_000, pctN, capN * 100))}</span>;
            on ₹5,00,000, by up to <span className="num text-ink">{inr(allowed(50_000_000, pctN, capN * 100))}</span>.
          </p>
        )}
        <div className="flex flex-wrap items-center gap-4 sm:col-span-2">
          <PillButton type="submit" disabled={!ok || !dirty || save.isPending}>{save.isPending ? "Saving…" : "Save tolerance"}</PillButton>
          {save.isSuccess && !dirty && <span role="status" className="text-[14px] text-approve">Saved. The next invoice uses it.</span>}
          {save.error && !Object.keys(errors).length && <span role="alert" className="text-[14px] text-reject">{save.error.message}</span>}
        </div>
      </form>
    </Section>
  )
}

function Emails({ s }: { s: AppSettings }) {
  const qc = useQueryClient()
  const save = useMutation({
    mutationFn: (on: boolean) => updateSettings({ vendor_auto_send: on }),
    onSuccess: (data) => qc.setQueryData(["settings"], data),
  })
  const on = save.isPending ? !!save.variables : s.vendor_auto_send
  return (
    <Section id="emails" title="Emails">
      <div className="flex max-w-2xl items-start justify-between gap-6 rounded-card border border-line bg-raised p-6">
        <div>
          <p id="auto-send-label" className="font-medium text-ink">Send vendor emails automatically</p>
          <p id="auto-send-desc" className="mt-1 text-[14px] leading-relaxed text-ink-2">
            On: when an invoice is held for something the vendor must fix, the email goes out at once. Off: it waits in
            the Outbox until someone in AP presses Send. Internal alerts always go out, and a vendor is never emailed
            about a fraud finding.
          </p>
          {!s.vendor_auto_send_allowed && (
            <p className="mt-2 text-[13px] text-hold">Vendor auto-send is switched off for this deployment, so vendor emails always wait in the Outbox.</p>
          )}
          {!s.emails_enabled && (
            <p className="mt-2 text-[13px] text-hold">Email sending is off for this deployment: every email stays as a draft in the Outbox.</p>
          )}
          {save.error && <p role="alert" className="mt-2 text-[13px] text-reject">{save.error.message}</p>}
        </div>
        <button type="button" role="switch" aria-checked={on} aria-labelledby="auto-send-label" aria-describedby="auto-send-desc"
          disabled={save.isPending} onClick={() => save.mutate(!on)}
          className={cn("relative mt-1 h-7 w-12 shrink-0 rounded-full border transition-colors duration-200",
            on ? "border-ink bg-ink" : "border-line bg-hover")}>
          <span aria-hidden className={cn("absolute top-1/2 left-1 size-5 -translate-y-1/2 rounded-full bg-raised shadow-sm transition-transform duration-200",
            on && "translate-x-5")} />
        </button>
      </div>
    </Section>
  )
}

function DemoData() {
  const qc = useQueryClient()
  const [typed, setTyped] = useState("")
  const reset = useMutation({
    mutationFn: resetDemo,
    onSuccess: () => {
      setTyped("")
      qc.invalidateQueries()
    },
  })
  return (
    <Section id="demo" title="Demo data">
      <div className="max-w-2xl rounded-card border border-reject/30 bg-reject-bg/40 p-6">
        <p className="font-medium text-ink">Reset demo data</p>
        <p className="mt-1 text-[14px] leading-relaxed text-ink-2">
          Deletes every processed invoice, email and review, every PO and vendor added here, and any settings changes,
          then restores the original POs, vendors and ledger. This can't be undone.
        </p>
        <form className="mt-5 flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); if (typed === "RESET") reset.mutate() }}>
          <Field label={<>Type <span className="text-ink">RESET</span> to confirm</>} htmlFor="reset-confirm" className="w-56">
            <input id="reset-confirm" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off"
              className={cn(inputCls, "font-mono")} />
          </Field>
          <PillButton type="submit" disabled={typed !== "RESET" || reset.isPending}
            className="bg-reject hover:bg-reject/85">
            {reset.isPending ? "Resetting…" : "Reset demo data"}
          </PillButton>
        </form>
        {reset.isSuccess && <p role="status" className="mt-3 text-[14px] text-approve">{reset.data.message}</p>}
        {reset.error && <p role="alert" className="mt-3 text-[14px] text-reject">{reset.error.message}</p>}
      </div>
    </Section>
  )
}
