import { useMemo, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"

import { ApiError, createVendor } from "@/api"
import { ProcurementOnly } from "@/components/ProcurementOnly"
import { Field, inputCls, invalidCls } from "@/components/ds/Field"
import { PillButton } from "@/components/ds/PillButton"
import { SectionTitle } from "@/components/ds/SectionTitle"
import { gstinProblem, normaliseGstin, stateLabel } from "@/lib/gstin"
import { cn } from "@/lib/utils"
import { useRole } from "@/role"
import type { VendorInput, VendorRow } from "@/types"

const EMPTY: VendorInput = {
  name: "", short_name: "", gstin: "", address: "", phone: "", bank_account: "", ifsc: "", bank_name: "",
  contact_email: "", msme: null,
}

/** Same checks as the server; duplicates (GSTIN, bank account) only the server can see. */
function validate(v: VendorInput): Record<string, string> {
  const e: Record<string, string> = {}
  if (!v.name.trim()) e.name = "Enter the vendor's legal name."
  const g = gstinProblem(v.gstin)
  if (g) e.gstin = g
  const account = v.bank_account.replace(/\s/g, "")
  if (!account) e.bank_account = "Enter the bank account the vendor is paid into."
  else if (!/^\d{9,18}$/.test(account)) e.bank_account = "A bank account number is 9 to 18 digits, nothing else."
  const ifsc = v.ifsc.trim().toUpperCase()
  if (!ifsc) e.ifsc = "Enter the branch IFSC."
  else if (!/^[A-Z]{4}0[A-Z0-9]{6}$/.test(ifsc))
    e.ifsc = "An IFSC is 11 characters: 4 letters for the bank, a zero, then 6 letters or digits (e.g. HDFC0001234)."
  if (!v.contact_email.trim()) e.contact_email = "Enter a contact email: it's where invoice problems are sent."
  else if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v.contact_email.trim())) e.contact_email = "That doesn't look like an email address."
  if (v.msme == null) e.msme = "Say whether the vendor is an MSME: it caps their payment terms at 45 days."
  return e
}

export function VendorForm({ onCancel, onCreated }: { onCancel: () => void; onCreated: (v: VendorRow) => void }) {
  const { role } = useRole()
  const qc = useQueryClient()
  const [form, setForm] = useState<VendorInput>(EMPTY)
  const [touched, setTouched] = useState<Set<string>>(new Set())
  const [tried, setTried] = useState(false)
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({})
  const errors = useMemo(() => validate(form), [form])

  const save = useMutation({
    mutationFn: (body: VendorInput) => createVendor(body, role),
    onSuccess: (v) => {
      qc.invalidateQueries({ queryKey: ["vendors"] })
      onCreated(v)
    },
    onError: (e) => setServerErrors(e instanceof ApiError ? e.errors : {}),
  })

  // A field shows its problem once the user has left it, or after they try to save.
  const shown = (k: string) => serverErrors[k] ?? (tried || touched.has(k) ? errors[k] : undefined)
  const set = (k: keyof VendorInput, value: string | boolean) => {
    setForm((f) => ({ ...f, [k]: value }))
    setServerErrors((s) => {
      if (!(k in s)) return s
      const next = { ...s }
      delete next[k]
      return next
    })
  }
  const blur = (k: string) => setTouched((t) => new Set(t).add(k))

  const gstin = normaliseGstin(form.gstin)
  const state = !gstinProblem(form.gstin) ? stateLabel(gstin.slice(0, 2)) : null
  const problems = Object.keys(serverErrors).length || (tried ? Object.keys(errors).length : 0)
  const banner = problems ? `Fix the ${problems} highlighted problem${problems === 1 ? "" : "s"} to add this vendor.` : save.error?.message

  const text = (k: keyof VendorInput, label: string, opts: { hint?: string; placeholder?: string; mono?: boolean; wide?: boolean; type?: string } = {}) => (
    <Field label={label} htmlFor={`v-${k}`} error={shown(k)} hint={opts.hint} className={opts.wide ? "md:col-span-2" : undefined}>
      <input id={`v-${k}`} type={opts.type ?? "text"} value={form[k] as string} placeholder={opts.placeholder}
        onChange={(e) => set(k, e.target.value)} onBlur={() => blur(k)}
        aria-invalid={!!shown(k) || undefined} aria-describedby={shown(k) || opts.hint ? `v-${k}-msg` : undefined}
        className={cn(inputCls, opts.mono && "font-mono text-[14px] uppercase placeholder:normal-case", shown(k) && invalidCls)} />
    </Field>
  )

  return (
    <form noValidate aria-labelledby="vendor-form-title"
      onSubmit={(e) => {
        e.preventDefault()
        setTried(true)
        if (!Object.keys(errors).length) save.mutate({ ...form, gstin, ifsc: form.ifsc.trim().toUpperCase() })
      }}>
      <SectionTitle id="vendor-form-title">Add vendor</SectionTitle>
      <p className="mt-3 max-w-prose text-[15px] leading-relaxed text-ink-2">
        Indian vendors. On save we refuse a GSTIN or bank account that's already on file for another vendor.
      </p>

      <div className="mt-8 grid gap-x-5 gap-y-5 md:grid-cols-2">
        {text("name", "Legal name", { placeholder: "e.g. Nandi Computers Private Limited", wide: true })}
        {text("short_name", "Short name", { hint: "Optional. Used in emails, e.g. “Nandi Computers”." })}
        {text("gstin", "GSTIN", { mono: true, placeholder: "15 characters", hint: state ? `State: ${state}` : "The state is read from the first two digits." })}
        {text("bank_account", "Bank account number", { placeholder: "9 to 18 digits", hint: "Shown masked everywhere else." })}
        {text("ifsc", "IFSC", { mono: true, placeholder: "e.g. HDFC0001234" })}
        {text("bank_name", "Bank and branch", { hint: "Optional." })}
        {text("contact_email", "Contact email", { type: "email", placeholder: "accounts@vendor.example" })}
        {text("phone", "Phone", { hint: "Optional. Finance calls this number to verify a bank change." })}
        <fieldset className="flex flex-col gap-1.5">
          <legend className="label mb-1.5">MSME</legend>
          <div className="flex gap-2">
            {([true, false] as const).map((yes) => (
              <button key={String(yes)} type="button" aria-pressed={form.msme === yes} onClick={() => set("msme", yes)}
                className={cn("h-11 min-w-20 rounded-full border px-5 font-mono text-[13px] transition-colors duration-200",
                  form.msme === yes ? "border-ink bg-ink text-white" : "border-line bg-raised text-ink hover:border-ink",
                  shown("msme") && form.msme == null && "border-reject/60")}>
                {yes ? "Yes" : "No"}
              </button>
            ))}
          </div>
          {shown("msme") ? <p role="alert" className="text-[13px] text-reject">{shown("msme")}</p>
            : <p className="text-[13px] text-ink-3">MSME vendors must be paid within 45 days.</p>}
        </fieldset>
        {text("address", "Address", { hint: "Optional.", wide: true })}
      </div>

      <div className="mt-8 flex flex-col gap-3">
        {banner && <p role="alert" className="text-[14px] text-reject">{banner}</p>}
        <div className="flex flex-wrap items-start gap-3">
          <ProcurementOnly action="add vendors">
            {(disabled) => <PillButton type="submit" disabled={disabled || save.isPending}>{save.isPending ? "Saving…" : "Add vendor"}</PillButton>}
          </ProcurementOnly>
          <PillButton type="button" variant="secondary" onClick={onCancel}>Cancel</PillButton>
        </div>
      </div>
    </form>
  )
}
