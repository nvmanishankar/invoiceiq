import { inputCls } from "@/components/ds/Field"
import { inr } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { Extraction } from "@/types"
import { FIELDS, rupeesToPaise, type FieldDef, type Values } from "./fields"


/** Extracted fields, editable. Low-confidence and missing required fields are outlined amber. */
export function FieldsForm({
  extraction,
  values,
  onChange,
  disabled,
}: {
  extraction: Extraction | null
  values: Values
  onChange: (key: string, value: string) => void
  disabled?: boolean
}) {
  const confidence = extraction?.confidence ?? {}
  return (
    <div className="grid gap-x-4 gap-y-4 sm:grid-cols-2">
      {FIELDS.map((f) => {
        const low = confidence[f.key] === "low"
        const missing = !!f.required && !(values[f.key] ?? "").trim()
        return (
          <Field key={f.key} def={f} value={values[f.key] ?? ""} flag={low ? "Low confidence" : missing ? "Missing" : null}
            onChange={(v) => onChange(f.key, v)} disabled={disabled} />
        )
      })}
    </div>
  )
}

function Field({ def, value, flag, onChange, disabled }: {
  def: FieldDef
  value: string
  flag: string | null
  onChange: (v: string) => void
  disabled?: boolean
}) {
  const id = `field-${def.key}`
  const hint = def.kind === "money" && value.trim() ? inr(rupeesToPaise(value)) : null
  return (
    <div className={cn("flex flex-col gap-1.5", (def.kind === "text" && def.key === "vendor_name") && "sm:col-span-2")}>
      <label htmlFor={id} className="flex items-baseline justify-between gap-2">
        <span className="label">{def.label}</span>
        {flag && <span className="font-mono text-[11px] font-medium text-hold">{flag}</span>}
      </label>
      <div className="relative">
        {def.kind === "money" && (
          <span aria-hidden className="pointer-events-none absolute top-1/2 left-4 -translate-y-1/2 text-ink-3">₹</span>
        )}
        <input
          id={id}
          type={def.kind === "date" ? "date" : "text"}
          inputMode={def.kind === "money" ? "decimal" : def.kind === "days" ? "numeric" : undefined}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          aria-invalid={flag ? true : undefined}
          className={cn(
            inputCls,
            def.kind === "money" && "num pl-8 text-right",
            (def.kind === "text" && /gstin|bank|ifsc|number|reference/.test(def.key)) && "font-mono text-[14px]",
            flag && "border-hold bg-hold-bg/50 ring-2 ring-hold/25 hover:border-hold",
          )}
        />
      </div>
      {hint && <span className="num text-right font-mono text-[12px] text-ink-3">{hint}</span>}
    </div>
  )
}
