import { useState, type ReactNode } from "react"
import { Link } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { ApiError, createPo, getNextPoId, getSettings, getTaxRates, getVendors } from "@/api"
import { ProcurementOnly } from "@/components/ProcurementOnly"
import { Field, inputCls, invalidCls } from "@/components/ds/Field"
import { PillButton } from "@/components/ds/PillButton"
import { SectionTitle } from "@/components/ds/SectionTitle"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { day, inr } from "@/lib/format"
import { cn } from "@/lib/utils"
import { useRole } from "@/role"
import type { PoInput, PoRow, TaxRate, VendorRow } from "@/types"
import { TAX_TYPE_WORDS, lineAmounts, poTotals, rupeesToPaise, taxTypeFor, toNumber } from "./calc"

const TERMS_PRESETS = [0, 15, 30, 45, 60, 90] as const
const MSME_MAX_TERMS = 45
const DEPARTMENTS = ["Administration", "Facilities", "Finance", "HR", "IT", "Marketing", "Operations"]
const UNITS = ["pcs", "nos", "ream", "box", "set", "kg", "litre", "metre", "trip", "hour", "month", "lot"]
const NO_DEPT = "none"
const TRIGGER = "h-11! w-full rounded-input! border-line bg-raised px-4 text-[15px] text-ink hover:border-ink-3"
const CELL_TRIGGER = "h-10! w-full rounded-input! border-line bg-raised px-3 text-[14px] text-ink hover:border-ink-3"
const CELL_INPUT = cn(inputCls, "h-10 px-3 text-[14px]")

type LineState = { key: number; description: string; hsn: string; qty: string; unit: string; price: string; rate: string }

let nextKey = 1
const blankLine = (): LineState => ({ key: nextKey++, description: "", hsn: "", qty: "", unit: "pcs", price: "", rate: "18" })

/** Same checks as the server, so problems show while typing. Keys match the server's error keys. */
function validate(vendorId: string, vendors: VendorRow[], poDate: string, today: string, terms: number | null,
                  lines: LineState[], rates: TaxRate[] | undefined): Record<string, string> {
  const e: Record<string, string> = {}
  const vendor = vendors.find((v) => v.vendor_id === vendorId)
  if (!vendorId) e.vendor_id = "Choose a vendor."
  else if (vendor && vendor.status !== "Active") e.vendor_id = `${vendor.name} is blocked, so no new POs can be raised for them.`
  if (!/^\d{4}-\d{2}-\d{2}$/.test(poDate)) e.po_date = "Enter the PO date."
  else if (poDate > today) e.po_date = `The PO date can't be in the future (today is ${day(today)}).`
  if (terms == null || !Number.isInteger(terms) || terms < 0 || terms > 365)
    e.payment_terms_days = "Payment terms are a whole number of days from 0 to 365."
  if (!lines.length) e.lines = "Add at least one line item."
  const allowed = new Set(rates?.map((r) => r.rate))
  lines.forEach((l, i) => {
    const n = i + 1
    const k = `lines.${i}`
    if (!l.description.trim()) e[`${k}.description`] = `Line ${n}: describe the item.`
    if (l.hsn.trim() && !/^\d{4}(\d{2}){0,2}$/.test(l.hsn.trim())) e[`${k}.hsn_code`] = `Line ${n}: an HSN/SAC code is 4, 6 or 8 digits (or leave it blank).`
    const q = toNumber(l.qty)
    if (q == null || q <= 0) e[`${k}.qty`] = `Line ${n}: quantity must be more than 0.`
    const p = rupeesToPaise(l.price)
    if (p == null || p <= 0) e[`${k}.unit_price`] = `Line ${n}: unit price must be more than ₹0.`
    if (!l.rate) e[`${k}.tax_rate`] = `Line ${n}: choose a tax rate.`
    else if (rates && !allowed.has(Number(l.rate)) && !e.po_date)
      e[`${k}.tax_rate`] = `Line ${n}: ${l.rate}% isn't a valid GST rate on ${day(poDate)}.`
  })
  return e
}

export function PoForm({ initialVendor, onCancel, onCreated }: {
  initialVendor?: string | null
  onCancel: () => void
  onCreated: (po: PoRow) => void
}) {
  const { role } = useRole()
  const qc = useQueryClient()
  const vendorsQ = useQuery({ queryKey: ["vendors"], queryFn: getVendors })
  const nextQ = useQuery({ queryKey: ["pos-next-id"], queryFn: getNextPoId })
  const settingsQ = useQuery({ queryKey: ["settings"], queryFn: getSettings })
  const today = nextQ.data?.today ?? new Date().toISOString().slice(0, 10)

  const [vendorId, setVendorId] = useState(initialVendor ?? "")
  const [poDate, setPoDate] = useState<string | null>(null) // null: follow the server's today
  const date = poDate ?? today
  const [preset, setPreset] = useState<number | "custom">(30)
  const [customTerms, setCustomTerms] = useState("")
  const [department, setDepartment] = useState(NO_DEPT)
  const [lines, setLines] = useState<LineState[]>(() => [blankLine()])
  const [tried, setTried] = useState(false)
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({})

  const validDate = /^\d{4}-\d{2}-\d{2}$/.test(date)
  const ratesQ = useQuery({ queryKey: ["tax-rates", date], queryFn: () => getTaxRates(date), enabled: validDate })

  const vendors = vendorsQ.data ?? []
  const active = vendors.filter((v) => v.status === "Active")
  const vendor = vendors.find((v) => v.vendor_id === vendorId) ?? null
  const split = vendor ? taxTypeFor(vendor, settingsQ.data?.company.state_code ?? null) : null
  const terms = preset === "custom" ? toNumber(customTerms) : preset
  const msmeWarning = vendor?.msme && terms != null && terms > MSME_MAX_TERMS

  const amounts = lines.map((l) => lineAmounts(toNumber(l.qty), rupeesToPaise(l.price), l.rate ? Number(l.rate) : null))
  const totals = poTotals(amounts, split)
  const errors = validate(vendorId, vendors, date, today, terms, lines, ratesQ.data)
  const shown = (key: string) => serverErrors[key] ?? (tried ? errors[key] : undefined)
  const clearServer = (...keys: string[]) =>
    setServerErrors((s) => (keys.some((k) => k in s) ? Object.fromEntries(Object.entries(s).filter(([k]) => !keys.includes(k))) : s))

  const save = useMutation({
    mutationFn: (body: PoInput) => createPo(body, role),
    onSuccess: (po) => {
      qc.invalidateQueries({ queryKey: ["pos"] })
      qc.invalidateQueries({ queryKey: ["pos-next-id"] })
      onCreated(po)
    },
    onError: (e) => setServerErrors(e instanceof ApiError ? e.errors : {}),
  })

  const setLine = (i: number, patch: Partial<LineState>) => {
    setLines((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)))
    clearServer(...Object.keys(patch).map((k) => `lines.${i}.${{ hsn: "hsn_code", price: "unit_price", rate: "tax_rate" }[k] ?? k}`))
  }

  const submit = () => {
    setTried(true)
    if (Object.keys(errors).length) return
    save.mutate({
      vendor_id: vendorId,
      po_date: date,
      payment_terms_days: terms,
      department: department === NO_DEPT ? null : department,
      lines: lines.map((l) => ({
        description: l.description.trim(),
        hsn_code: l.hsn.trim() || null,
        qty: toNumber(l.qty),
        unit: l.unit,
        unit_price: toNumber(l.price.replace(/₹/g, "")),
        tax_rate: l.rate ? Number(l.rate) : null,
      })),
    })
  }

  const problems = Object.keys(serverErrors).length || (tried ? Object.keys(errors).length : 0)
  const banner = problems ? `Fix the ${problems} highlighted problem${problems === 1 ? "" : "s"} to save this PO.` : save.error?.message

  return (
    <form noValidate onSubmit={(e) => { e.preventDefault(); submit() }} aria-labelledby="po-form-title">
      <SectionTitle id="po-form-title" aside={<span className="font-mono text-[13px] text-ink-3">{nextQ.data?.po_id ?? "PO-…"} · assigned on save</span>}>
        New purchase order
      </SectionTitle>

      <div className="mt-8 grid gap-x-5 gap-y-5 md:grid-cols-2">
        <Field label="Vendor" htmlFor="po-vendor" error={shown("vendor_id")}
          hint={<>Active vendors only. Not listed? <Link to="/vendors?add=1" className="text-accent underline-offset-2 hover:underline">Add new vendor</Link></>}>
          <Select value={vendorId} onValueChange={(v) => { setVendorId(v); clearServer("vendor_id") }}>
            <SelectTrigger id="po-vendor" aria-invalid={!!shown("vendor_id") || undefined} className={cn(TRIGGER, shown("vendor_id") && invalidCls)}>
              <SelectValue placeholder={vendorsQ.isLoading ? "Loading vendors…" : "Choose a vendor"}>{vendor?.name}</SelectValue>
            </SelectTrigger>
            <SelectContent position="popper" sideOffset={6} className="rounded-input shadow-float">
              {active.map((v) => (
                <SelectItem key={v.vendor_id} value={v.vendor_id} className="py-2">
                  <span className="flex flex-col items-start gap-0.5">
                    <span className="text-[14px] text-ink">{v.name}</span>
                    <span className="font-mono text-[11px] text-ink-3">{v.gstin} · {v.state}{v.msme ? " · MSME" : ""}</span>
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>

        <div className="flex flex-col gap-1.5">
          <span className="label">GSTIN, state and tax</span>
          <div className="flex min-h-11 flex-col justify-center rounded-input border border-dashed border-line px-4 py-2 text-[14px]">
            {vendor ? (
              <>
                <span className="font-mono text-[13px] text-ink">{vendor.gstin} · {vendor.state}</span>
                <span className="text-ink-2">
                  {TAX_TYPE_WORDS[split!]}
                  {split === "CGST+SGST" && " (same state as us)"}
                  {split === "IGST" && ` (${settingsQ.data?.company.state ?? "our state"} is different)`}
                </span>
              </>
            ) : (
              <span className="text-ink-3">Filled in from the vendor master</span>
            )}
          </div>
        </div>

        <Field label="PO date" htmlFor="po-date" error={shown("po_date")} hint="Today by default; can't be in the future.">
          <input id="po-date" type="date" value={date} max={today}
            onChange={(e) => { setPoDate(e.target.value); clearServer("po_date") }}
            aria-invalid={!!shown("po_date") || undefined} className={cn(inputCls, shown("po_date") && invalidCls)} />
        </Field>

        <Field label="Department" htmlFor="po-dept" hint="Optional.">
          <Select value={department} onValueChange={setDepartment}>
            <SelectTrigger id="po-dept" className={TRIGGER}><SelectValue /></SelectTrigger>
            <SelectContent position="popper" sideOffset={6} className="rounded-input shadow-float">
              <SelectItem value={NO_DEPT}>No department</SelectItem>
              {DEPARTMENTS.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
            </SelectContent>
          </Select>
        </Field>

        <div className="flex flex-col gap-1.5 md:col-span-2">
          <span id="po-terms-label" className="label">Payment terms (days)</span>
          <div role="group" aria-labelledby="po-terms-label" className="flex flex-wrap items-center gap-2">
            {TERMS_PRESETS.map((d) => (
              <TermsPill key={d} active={preset === d} onClick={() => { setPreset(d); clearServer("payment_terms_days") }}>{d}</TermsPill>
            ))}
            <TermsPill active={preset === "custom"} onClick={() => setPreset("custom")}>Custom</TermsPill>
            {preset === "custom" && (
              <input aria-label="Custom payment terms in days" inputMode="numeric" value={customTerms} placeholder="e.g. 21"
                onChange={(e) => { setCustomTerms(e.target.value); clearServer("payment_terms_days") }}
                className={cn(inputCls, "h-9 w-28 px-3 text-[14px]", shown("payment_terms_days") && invalidCls)} />
            )}
          </div>
          {shown("payment_terms_days") && <p role="alert" className="text-[13px] text-reject">{shown("payment_terms_days")}</p>}
          {msmeWarning && (
            <p className="mt-1 rounded-input border border-hold/30 bg-hold-bg px-4 py-2.5 text-[13px] leading-relaxed text-ink">
              {vendor!.name} is an MSME: the law caps payment at {MSME_MAX_TERMS} days, so their invoices will fall due
              after {MSME_MAX_TERMS} days, not {terms}.
            </p>
          )}
        </div>
      </div>

      <div className="mt-10">
        <div className="flex items-center justify-between gap-4">
          <p className="label">Line items · prices excl. GST</p>
          <PillButton type="button" variant="secondary" className="h-9 px-4" onClick={() => setLines((ls) => [...ls, blankLine()])}>
            + Add item
          </PillButton>
        </div>
        {shown("lines") && <p role="alert" className="mt-2 text-[13px] text-reject">{shown("lines")}</p>}
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[820px] border-collapse text-[14px]">
            <thead>
              <tr className="border-b border-line">
                {["Description", "HSN", "Qty", "Unit", "Unit price", "GST", "Line total", ""].map((h, i) => (
                  <th key={i} scope="col" className={cn("label px-1.5 py-2 text-left font-normal", i >= 6 && "text-right")}>
                    {h || <span className="sr-only">Remove</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {lines.map((l, i) => {
                const k = `lines.${i}`
                const bad = (f: string) => shown(`${k}.${f}`)
                const lineErrors = ["description", "hsn_code", "qty", "unit", "unit_price", "tax_rate"].map(bad).filter(Boolean)
                const a = amounts[i]
                return (
                  <tr key={l.key} className="border-b border-line align-top last:border-b-0">
                    <td className="min-w-64 px-1.5 py-2">
                      <input aria-label={`Line ${i + 1} description`} value={l.description} placeholder="e.g. Dell Latitude 5440 laptop, i5, 16GB"
                        onChange={(e) => setLine(i, { description: e.target.value })}
                        className={cn(CELL_INPUT, bad("description") && invalidCls)} />
                      {lineErrors.length > 0 && (
                        <ul role="alert" className="mt-1.5 flex flex-col gap-0.5 text-[12px] leading-snug text-reject">
                          {lineErrors.map((m) => <li key={m}>{m}</li>)}
                        </ul>
                      )}
                    </td>
                    <td className="w-20 px-1.5 py-2">
                      <input aria-label={`Line ${i + 1} HSN code`} value={l.hsn} inputMode="numeric" placeholder="—"
                        onChange={(e) => setLine(i, { hsn: e.target.value })}
                        className={cn(CELL_INPUT, "font-mono", bad("hsn_code") && invalidCls)} />
                    </td>
                    <td className="w-20 px-1.5 py-2">
                      <input aria-label={`Line ${i + 1} quantity`} value={l.qty} inputMode="decimal" placeholder="0"
                        onChange={(e) => setLine(i, { qty: e.target.value })}
                        className={cn(CELL_INPUT, "num text-right", bad("qty") && invalidCls)} />
                    </td>
                    <td className="w-24 px-1.5 py-2">
                      <Select value={l.unit} onValueChange={(v) => setLine(i, { unit: v })}>
                        <SelectTrigger aria-label={`Line ${i + 1} unit`} className={CELL_TRIGGER}><SelectValue /></SelectTrigger>
                        <SelectContent position="popper" sideOffset={6} className="rounded-input shadow-float">
                          {UNITS.map((u) => <SelectItem key={u} value={u}>{u}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </td>
                    <td className="w-32 px-1.5 py-2">
                      <div className="relative">
                        <span aria-hidden className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-ink-3">₹</span>
                        <input aria-label={`Line ${i + 1} unit price in rupees, excluding GST`} value={l.price} inputMode="decimal" placeholder="0"
                          onChange={(e) => setLine(i, { price: e.target.value })}
                          className={cn(CELL_INPUT, "num pl-7 text-right", bad("unit_price") && invalidCls)} />
                      </div>
                    </td>
                    <td className="w-28 px-1.5 py-2">
                      <Select value={l.rate} onValueChange={(v) => setLine(i, { rate: v })}>
                        <SelectTrigger aria-label={`Line ${i + 1} GST rate`} aria-invalid={!!bad("tax_rate") || undefined}
                          className={cn(CELL_TRIGGER, bad("tax_rate") && invalidCls)}>
                          <SelectValue placeholder="Rate">{l.rate ? `${l.rate}%` : undefined}</SelectValue>
                        </SelectTrigger>
                        <SelectContent position="popper" sideOffset={6} className="rounded-input shadow-float">
                          {(ratesQ.data ?? []).map((r) => (
                            <SelectItem key={r.id} value={String(r.rate)}>
                              <span className="num">{r.rate}%</span> <span className="text-ink-3">{r.label}</span>
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </td>
                    <td className="num w-28 px-1.5 py-2 text-right leading-10 whitespace-nowrap text-ink">{a ? inr(a.taxable + a.tax) : "—"}</td>
                    <td className="w-10 py-2 pl-1.5 text-right">
                      <button type="button" aria-label={`Remove line ${i + 1}`} disabled={lines.length === 1}
                        onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))}
                        className="grid size-10 place-items-center rounded-full font-mono text-[16px] text-ink-3 transition-colors hover:bg-hover hover:text-reject disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-ink-3">
                        ×
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="mt-8 flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="flex flex-col gap-3">
          {banner && <p role="alert" className="text-[14px] text-reject">{banner}</p>}
          <div className="flex flex-wrap items-start gap-3">
            <ProcurementOnly action="raise purchase orders">
              {(disabled) => <PillButton type="submit" disabled={disabled || save.isPending}>{save.isPending ? "Saving…" : "Create PO"}</PillButton>}
            </ProcurementOnly>
            <PillButton type="button" variant="secondary" onClick={onCancel}>Cancel</PillButton>
          </div>
        </div>
        <dl aria-live="polite" className="num w-full rounded-card border border-line bg-raised p-5 text-[14px] lg:w-80">
          <Row k="Subtotal" v={inr(totals.subtotal)} />
          {split === "CGST+SGST" && <><Row k="CGST" v={inr(totals.cgst)} /><Row k="SGST" v={inr(totals.sgst)} /></>}
          {split === "IGST" && <Row k="IGST" v={inr(totals.igst)} />}
          {split === "Import" && <Row k="GST" v="None from the vendor" />}
          {!split && <Row k="GST" v={inr(totals.tax)} note="split shown once a vendor is chosen" />}
          <div className="mt-3 flex items-baseline justify-between border-t border-line pt-3">
            <dt className="text-ink">Total</dt>
            <dd className="text-[22px] font-medium tracking-[-0.01em] text-ink">{inr(totals.total)}</dd>
          </div>
        </dl>
      </div>
    </form>
  )
}

function Row({ k, v, note }: { k: string; v: string; note?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1">
      <dt className="text-ink-2">{k}{note && <span className="block text-[12px] text-ink-3">{note}</span>}</dt>
      <dd className="text-ink">{v}</dd>
    </div>
  )
}

function TermsPill({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" aria-pressed={active} onClick={onClick}
      className={cn("h-9 min-w-12 rounded-full border px-4 font-mono text-[13px] transition-colors duration-200",
        active ? "border-ink bg-ink text-white" : "border-line bg-raised text-ink hover:border-ink")}>
      {children}
    </button>
  )
}
