import { useState } from "react"
import { useQuery } from "@tanstack/react-query"

import { getSettings, getTaxHistory, getTaxRates } from "@/api"
import { inputCls } from "@/components/ds/Field"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { day, inr } from "@/lib/format"
import { STATE_NAMES } from "@/lib/gstin"
import { cn } from "@/lib/utils"
import type { Catalogue, TaxRate } from "@/types"
import { CaseCodeChip, OutcomeChip, Section } from "./shared"

const TRIGGER = "h-11! w-full rounded-input! border-line bg-raised px-4 text-[15px] text-ink hover:border-ink-3"
const ABROAD = "abroad"
const STATES = Object.entries(STATE_NAMES).sort((a, b) => a[1].localeCompare(b[1]))
const NEW_SLABS = "2025-09-22"

function isoToday() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

const pct = (r: number) => `${r % 1 ? r.toFixed(1) : r}%`

export function GstSection({ catalogue, onCase }: { catalogue: Catalogue | undefined; onCase: (code: string) => void }) {
  const today = isoToday()
  const settings = useQuery({ queryKey: ["settings"], queryFn: getSettings })
  const rates = useQuery({ queryKey: ["tax-rates", today], queryFn: () => getTaxRates(today) })
  const history = useQuery({ queryKey: ["how", "tax-history"], queryFn: getTaxHistory, staleTime: Infinity })
  const ours = settings.data?.company.state_code ?? null
  const oursName = ours ? (STATE_NAMES[ours] ?? `state ${ours}`) : "our state"
  const [vendorState, setVendorState] = useState("29")
  const [raw, setRaw] = useState("100000")
  const [rate, setRate] = useState<number | null>(null)
  const available = (rates.data ?? []).map((r) => r.rate).sort((a, b) => a - b)
  const chosen = rate ?? (available.includes(18) ? 18 : available[0] ?? null)

  const rupees = Number(raw.replace(/[,\s₹]/g, ""))
  const valid = raw.trim() !== "" && Number.isFinite(rupees) && rupees >= 0
  const taxable = valid ? Math.round(rupees * 100) : 0
  const abroad = vendorState === ABROAD
  const same = !abroad && vendorState === ours
  const tax = abroad || chosen == null ? 0 : Math.round((taxable * chosen) / 100)
  const half = Math.round(tax / 2)
  const vName = abroad ? "a vendor outside India" : STATE_NAMES[vendorState]

  let parts: { label: string; paise: number; cls: string }[] = []
  let why = ""
  if (abroad) {
    why = "A vendor outside India charges no Indian GST. We pay it ourselves: through customs for goods, or by reverse charge for services."
  } else if (chosen === 0) {
    why = "This rate is nil, so no GST is charged at all."
  } else if (same) {
    parts = [
      { label: `CGST ${pct(chosen! / 2)}`, paise: half, cls: "bg-accent" },
      { label: `SGST ${pct(chosen! / 2)}`, paise: tax - half, cls: "bg-accent/60" },
    ]
    why = `${vName} is our state too, so the GST is split in two equal halves: CGST for the central government and SGST for ${oursName}.`
  } else {
    parts = [{ label: `IGST ${pct(chosen!)}`, paise: tax, cls: "bg-accent" }]
    why = `${vName} isn't ${oursName}, so it's one IGST line. The centre collects it and passes the state's share on to ${oursName}, where the goods are used.`
  }
  const total = taxable + tax

  const checks = (catalogue?.cases ?? []).filter((c) => c.stage === 8 && c.code !== "8.8")

  return (
    <Section
      id="gst"
      kicker="07 · GST"
      title="GST in plain words"
      lede={<>GST is India's tax on goods and services. The vendor adds it on top of the price and the buyer claims it back later, but only if the invoice charges it the right way. We're in <b className="font-medium text-ink">{oursName}</b>.</>}
    >
      <div className="grid gap-5 rounded-card border border-line bg-raised p-5 lg:grid-cols-[280px_minmax(0,1fr)]">
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="gst-state" className="label">Vendor's state</label>
            <Select value={vendorState} onValueChange={setVendorState}>
              <SelectTrigger id="gst-state" className={TRIGGER}><SelectValue /></SelectTrigger>
              <SelectContent position="popper" sideOffset={6} className="max-h-72 rounded-input shadow-float">
                {STATES.map(([code, name]) => (
                  <SelectItem key={code} value={code}>
                    <span className="flex items-center gap-2">{name}<span className="font-mono text-[11px] text-ink-3">{code}</span></span>
                  </SelectItem>
                ))}
                <SelectItem value={ABROAD}>Outside India</SelectItem>
              </SelectContent>
            </Select>
            <p className="font-mono text-[11px] text-ink-3">The first 2 digits of a GSTIN are the state code.</p>
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="gst-amount" className="label">Price before tax (₹)</label>
            <input id="gst-amount" inputMode="decimal" value={raw} onChange={(e) => setRaw(e.target.value)} className={cn(inputCls, "num font-mono")} />
          </div>
          <div className="flex flex-col gap-1.5">
            <span id="gst-rate-label" className="label">Rate (valid today)</span>
            <div role="radiogroup" aria-labelledby="gst-rate-label" className="flex flex-wrap gap-1.5">
              {available.map((r) => (
                <button key={r} type="button" role="radio" aria-checked={chosen === r} onClick={() => setRate(r)}
                  className={cn("h-9 min-w-12 rounded-full border px-3 font-mono text-[13px] transition-colors duration-200",
                    chosen === r ? "border-ink bg-ink text-white" : "border-line bg-raised text-ink hover:border-ink")}>
                  {r}%
                </button>
              ))}
              {rates.isError && <p className="text-[13px] text-hold">Couldn't load the rates.</p>}
            </div>
          </div>
        </div>

        <div aria-live="polite" className="flex flex-col gap-4">
          {!valid ? <p className="text-[14px] text-hold">Type a price in rupees, like 1,00,000.</p> : (
            <>
              <div className="flex h-12 overflow-hidden rounded-[14px] border border-line">
                <div className="flex items-center bg-hover px-3 font-mono text-[12px] text-ink" style={{ flexGrow: taxable || 1 }}>Price</div>
                {parts.map((p) => (
                  <div key={p.label} className={cn("flex min-w-16 items-center justify-center px-2 font-mono text-[11px] text-white", p.cls)} style={{ flexGrow: Math.max(p.paise, total * 0.08) }}>
                    {p.label}
                  </div>
                ))}
              </div>
              <dl className="num grid grid-cols-[minmax(0,1fr)_auto] gap-x-6 gap-y-1.5 font-mono text-[14px]">
                <dt className="text-ink-2">Price</dt><dd className="text-right text-ink">{inr(taxable)}</dd>
                {parts.map((p) => (
                  <div key={p.label} className="contents"><dt className="text-ink-2">{p.label}</dt><dd className="text-right text-ink">{inr(p.paise)}</dd></div>
                ))}
                {!parts.length && <><dt className="text-ink-2">GST</dt><dd className="text-right text-ink">{inr(0)}</dd></>}
                <dt className="border-t border-line pt-1.5 font-medium text-ink">Invoice total</dt>
                <dd className="border-t border-line pt-1.5 text-right font-semibold text-ink">{inr(total)}</dd>
              </dl>
              <p className="rounded-card bg-bubble px-4 py-3 font-mono text-[13.5px] leading-[1.6] text-ink">{why}</p>
              {!abroad && chosen !== 0 && (
                <p className="text-[13px] text-ink-2">
                  Same total either way. The split only decides which government gets the money, and a wrong split means the invoice must be reissued.
                </p>
              )}
            </>
          )}
        </div>
      </div>

      <Timeline rates={history.data} today={today} />

      <h3 className="mt-10 text-h3">What the tax check verifies</h3>
      <ul className="mt-4 flex flex-col divide-y divide-line rounded-card border border-line bg-raised">
        {checks.map((c) => (
          <li key={c.code}>
            <button type="button" onClick={() => onCase(c.code)} aria-label={`${c.code} ${c.title}: show in the 9 checks`}
              className="grid w-full grid-cols-[auto_minmax(0,1fr)] items-start gap-x-3 gap-y-1 px-4 py-3 text-left hover:bg-hover/60 md:grid-cols-[auto_200px_minmax(0,1fr)_auto]">
              <CaseCodeChip c={c} />
              <span className="text-[14px] font-medium text-ink">{c.title}</span>
              <span className="col-span-2 text-[13px] leading-snug text-ink-2 md:col-span-1">{c.trigger}</span>
              <span className="col-start-2 md:col-start-auto"><OutcomeChip outcome={c.outcome} also={c.also} /></span>
            </button>
          </li>
        ))}
      </ul>
    </Section>
  )
}

function Timeline({ rates, today }: { rates: TaxRate[] | undefined; today: string }) {
  const [sel, setSel] = useState<number | null>(12)
  if (!rates?.length) return null
  const start = Math.min(...rates.map((r) => Date.parse(r.valid_from)))
  const end = Date.parse(today)
  const x = (iso: string | null) => ((Math.min(iso ? Date.parse(iso) : end, end) - start) / (end - start)) * 100
  const picked = rates.find((r) => r.rate === sel) ?? null
  const years = [2018, 2020, 2022, 2024, 2026]

  return (
    <div className="mt-10">
      <h3 className="text-h3">Rates change</h3>
      <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ink-2">
        GST was simplified on 22 Sep 2025: the 12% and 28% slabs ended on 21 Sep 2025, and a 40% slab began. An invoice is checked against the rates valid on its own date. Pick a rate.
      </p>
      <div className="mt-5 rounded-card border border-line bg-raised p-5">
        <div className="relative">
          <div className="absolute top-0 bottom-6 w-px bg-ink" style={{ left: `calc(56px + (100% - 56px) * ${x(NEW_SLABS) / 100})` }} aria-hidden />
          <ul className="flex flex-col gap-1.5">
            {rates.map((r) => {
              const ended = !!r.valid_to
              return (
                <li key={r.id}>
                  <button type="button" aria-pressed={sel === r.rate} onClick={() => setSel(r.rate)}
                    className="grid w-full grid-cols-[48px_minmax(0,1fr)] items-center gap-2 rounded-full text-left">
                    <span className={cn("font-mono text-[12px]", sel === r.rate ? "font-semibold text-ink" : "text-ink-2")}>{r.rate}%</span>
                    <span className="relative h-5">
                      <span
                        className={cn("absolute inset-y-0 rounded-full transition-colors duration-200",
                          ended ? "bg-hold/70" : "bg-ink-2", sel === r.rate && (ended ? "bg-hold" : "bg-ink"))}
                        style={{ left: `${x(r.valid_from)}%`, width: `${Math.max(1, x(r.valid_to) - x(r.valid_from))}%` }}
                      />
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
          <div className="relative mt-2 ml-[56px] h-4 font-mono text-[10.5px] text-ink-3" aria-hidden>
            {years.map((y) => (
              <span key={y} className="absolute -translate-x-1/2" style={{ left: `${x(`${y}-01-01`)}%` }}>{y}</span>
            ))}
          </div>
        </div>
        {picked && (
          <p aria-live="polite" className="mt-4 rounded-card bg-bubble px-4 py-3 font-mono text-[13px] leading-[1.6] text-ink">
            {picked.rate}%{picked.label ? ` · ${picked.label}` : ""} · from {day(picked.valid_from)}{picked.valid_to ? ` to ${day(picked.valid_to)}` : ", still valid"}.
            {picked.valid_to ? ` An invoice at ${picked.rate}% dated after ${day(picked.valid_to)} is held (8.5).` : ""}
          </p>
        )}
      </div>
    </div>
  )
}
