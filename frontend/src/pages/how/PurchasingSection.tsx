import { useState, type ReactNode } from "react"
import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"

import { getTaxRates, getVendors } from "@/api"
import { inputCls } from "@/components/ds/Field"
import { day } from "@/lib/format"
import { gstinProblem, normaliseGstin, stateLabel } from "@/lib/gstin"
import { cn } from "@/lib/utils"
import type { HowFacts } from "@/types"
import { Card, Section, Segmented } from "./shared"
import { SHOTS } from "./shots"
import { Shot } from "./Shot"

type Which = "po" | "vendor"

const todayIso = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

export function PurchasingSection({ facts }: { facts: HowFacts | undefined }) {
  const [which, setWhich] = useState<Which>("po")
  return (
    <Section
      id="purchasing"
      kicker="10 · POs and vendors"
      title="Creating a PO and a vendor"
      lede="Every invoice is checked against the POs and the vendor list, so both only come in as typed, checked data. Only Procurement can add or change them: see Roles below."
    >
      <Segmented label="Show" value={which} onChange={setWhich}
        options={[{ value: "po", label: "Create a PO" }, { value: "vendor", label: "Add a vendor" }]} />
      <div className="mt-5">
        {which === "po" ? <CreatePo facts={facts} /> : <AddVendor />}
      </div>
    </Section>
  )
}

function Steps({ items }: { items: ReactNode[] }) {
  return (
    <ol className="flex flex-col">
      {items.map((it, i) => (
        <li key={i} className="flex gap-4 border-t border-line py-3.5 first:border-t-0 first:pt-0">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-ink font-mono text-[12px] text-white">{i + 1}</span>
          <p className="pt-0.5 text-[15px] leading-relaxed text-ink">{it}</p>
        </li>
      ))}
    </ol>
  )
}

function Check({ tone = "refuse", title, children }: { tone?: "refuse" | "warn" | "fraud"; title: string; children: ReactNode }) {
  const word = { refuse: "Refused", warn: "Warning only", fraud: "Refused · fraud signal" }[tone]
  return (
    <li className={cn("rounded-[14px] border px-4 py-3", tone === "fraud" ? "border-reject/30 bg-reject-bg" : "border-line")}>
      <p className="flex flex-wrap items-baseline gap-x-2">
        <span className="text-[15px] font-medium text-ink">{title}</span>
        <span className={cn("font-mono text-[11px] tracking-[0.06em] uppercase", tone === "warn" ? "text-hold" : "text-reject")}>{word}</span>
      </p>
      <p className="mt-1 text-[14px] leading-relaxed text-ink-2">{children}</p>
    </li>
  )
}

function CreatePo({ facts }: { facts: HowFacts | undefined }) {
  const today = todayIso()
  const rates = useQuery({ queryKey: ["tax-rates", today], queryFn: () => getTaxRates(today) })
  const year = today.slice(0, 4)
  const msme = facts?.msme_max_terms_days ?? 45
  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Card>
          <p className="label mb-4">Steps</p>
          <Steps items={[
            <>Switch the role at the top to <b className="font-medium">Procurement</b>. For other roles the button is greyed out, with the reason under it.</>,
            <>Open <Link to="/pos" className="underline underline-offset-2 hover:text-accent">Purchase orders</Link> and press <b className="font-medium">Create PO</b>. The next number, like PO-{year}-{facts?.first_new_po ?? "…"}, is shown; it's only taken when you save.</>,
            <>Choose an active vendor. Their GSTIN, state and the kind of GST fill in: CGST + SGST in our state, IGST from another.</>,
            <>Set the PO date (today by default), payment terms from 0 to {facts?.max_terms_days ?? "…"} days, and a department if you like.</>,
            <>Add the lines: description, quantity, unit, price before GST and the GST rate. The HSN code is optional.</>,
            <>Press <b className="font-medium">Create PO</b>. It's saved as Open with your role as its creator, and invoices can match it straight away.</>,
          ]} />
        </Card>
        <div className="flex flex-col gap-3">
          <p className="label">What's checked on save</p>
          <ul className="flex flex-col gap-2">
            <Check title="Active vendor">A blocked vendor can't get a new PO. The list only offers active vendors, and the server refuses a blocked one anyway.</Check>
            <Check title="Valid GST rate for the date">
              Each line's rate must be in force on the PO date.{" "}
              {rates.data && <>Valid on {day(today)}: <span className="num font-mono text-ink">{rates.data.map((r) => `${r.rate}%`).join(", ")}</span>. </>}
              12% and 28% ended after 21 Sep 2025.
            </Check>
            <Check tone="warn" title={`MSME ${msme}-day cap`}>
              A small business (MSME) must be paid within {msme} days by law. Longer terms still save, with a warning: invoices will fall due after {msme} days.
            </Check>
            <Check title="Date and lines">The PO date can't be in the future. At least one line, each with a description, quantity above 0, a unit and a price above ₹0.</Check>
          </ul>
        </div>
      </div>
      <Shot {...SHOTS.createPo}
        alt="The Create PO form as Procurement: vendor, tax type filled in, date, terms and a line with a GST rate"
        caption="Create PO, signed in as Procurement. The vendor's tax type fills in, and the GST list only offers rates valid on the PO date." />
    </div>
  )
}

function AddVendor() {
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="flex flex-col gap-5">
        <Card>
          <p className="label mb-4">Steps</p>
          <Steps items={[
            <>As <b className="font-medium">Procurement</b>, open <Link to="/vendors" className="underline underline-offset-2 hover:text-accent">Vendors</Link> and press <b className="font-medium">Add vendor</b>. The PO form links here too.</>,
            <>Fill in the legal name, GSTIN, bank account, IFSC and contact email, and say whether they're an MSME. Short name, address, phone and bank name are optional.</>,
            <>Press <b className="font-medium">Add vendor</b>. They get the next id (V-…), start Active, and can be chosen on a PO at once.</>,
          ]} />
        </Card>
        <GstinTry />
      </div>
      <div className="flex flex-col gap-3">
        <p className="label">What's checked on save</p>
        <ul className="flex flex-col gap-2">
          <Check title="GSTIN">15 characters in the right shape, a real Indian state code, and a matching check character, so one typo is caught.</Check>
          <Check title="IFSC">11 characters: 4 letters for the bank, a zero, then 6 letters or digits (e.g. HDFC0001234).</Check>
          <Check title="Bank account">9 to 18 digits, nothing else.</Check>
          <Check title="Contact email and MSME">A contact email is required. MSME must be answered yes or no, because it caps payment terms.</Check>
          <Check tone="fraud" title="Duplicate GSTIN">A GSTIN that already belongs to another vendor, blocked ones included.</Check>
          <Check tone="fraud" title="Duplicate bank account">An account already on file for another vendor. Two vendors paid into one account is a classic fraud signal, so it can't be added.</Check>
        </ul>
      </div>
    </div>
  )
}

/** The vendor form's own GSTIN check, plus the duplicate check against the live vendor list. */
function GstinTry() {
  const vendors = useQuery({ queryKey: ["vendors"], queryFn: getVendors })
  const [raw, setRaw] = useState("36AABCA1234F1ZA")
  const g = normaliseGstin(raw)
  const problem = gstinProblem(raw)
  const taken = !problem ? vendors.data?.find((v) => v.gstin === g) : undefined
  const examples = [
    ["New and valid", "27AAACS1234K1ZH"],
    ["Already taken", "36AABCA1234F1ZA"],
    ["One typo", "36AABCA1234F1ZB"],
    ["Bad state", "99AABCA1234F1ZA"],
  ]
  return (
    <Card>
      <label htmlFor="try-gstin" className="label">Try the GSTIN check</label>
      <input id="try-gstin" value={raw} onChange={(e) => setRaw(e.target.value)} spellCheck={false} autoComplete="off"
        className={cn(inputCls, "mt-2 font-mono tracking-[0.04em]")} />
      <div className="mt-2 flex flex-wrap gap-1.5">
        {examples.map(([label, v]) => (
          <button key={label} type="button" onClick={() => setRaw(v)}
            className="h-7 rounded-full border border-line px-2.5 font-mono text-[11px] text-ink-2 hover:border-ink">{label}</button>
        ))}
      </div>
      <p aria-live="polite" className={cn("mt-3 text-[14px] leading-relaxed", problem || taken ? "text-reject" : "text-approve")}>
        {problem ?? (taken
          ? `This GSTIN already belongs to ${taken.name} (${taken.vendor_id}).`
          : `Looks right: ${stateLabel(g.slice(0, 2))}, not used by any vendor yet.`)}
      </p>
      <p className="mt-1 text-[12px] text-ink-3">The same check the Add vendor form and the server run.</p>
    </Card>
  )
}
