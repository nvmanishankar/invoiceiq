import { SectionTitle } from "@/components/ds/SectionTitle"
import { qty } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { ComparisonRow } from "@/types"

const TINT = "bg-hold-bg text-hold"

/** Invoice line next to the PO line it matched. Anything that doesn't line up is tinted. */
export function CompareTable({ rows, poId }: { rows: ComparisonRow[]; poId: string | null }) {
  if (!rows.length) return null
  return (
    <section aria-labelledby="compare-title">
      <SectionTitle id="compare-title">Invoice vs {poId ?? "PO"}</SectionTitle>
      <div className="mt-6 overflow-x-auto rounded-card border border-line bg-raised">
        <table className="w-full border-collapse text-[14px]">
          <thead>
            <tr className="border-b border-line">
              <th scope="col" className="label px-4 py-3 text-left font-normal">Invoice line</th>
              <th scope="col" className="label px-4 py-3 text-left font-normal">PO line</th>
              <th scope="col" className="label px-4 py-3 text-right font-normal">Qty</th>
              <th scope="col" className="label px-4 py-3 text-right font-normal">Open on PO</th>
              <th scope="col" className="label px-4 py-3 text-right font-normal">Unit price</th>
              <th scope="col" className="label px-4 py-3 text-right font-normal">PO price</th>
              <th scope="col" className="label px-4 py-3 text-right font-normal">Amount</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const il = r.invoice_line
              const pl = r.po_line
              const missing = !il || !pl
              const overQty = il?.qty != null && pl != null && il.qty > pl.remaining_qty_before
              const priceOff = r.unit_price_diff_paise != null && r.unit_price_diff_paise !== 0
              const cell = "px-4 py-3 align-top"
              const num = `${cell} num text-right`
              return (
                <tr key={i} className="border-b border-line last:border-b-0 hover:bg-hover/60" data-mismatch={missing || overQty || priceOff || undefined}>
                  <td className={cn(cell, "text-ink", !il && TINT)}>{il?.description ?? "Not on the invoice"}</td>
                  <td className={cn(cell, "text-ink-2", !pl && TINT)}>{pl ? `${pl.line_no}. ${pl.description}` : "Not on the PO"}</td>
                  <td className={cn(num, "text-ink", overQty && TINT)}>{qty(il?.qty)} {il?.unit && <span className="text-ink-3">{il.unit}</span>}</td>
                  <td className={cn(num, "text-ink-2", overQty && TINT)}>
                    {pl ? <>{qty(pl.remaining_qty_before)} <span className="text-ink-3">of {qty(pl.qty)}</span></> : "—"}
                  </td>
                  <td className={cn(num, "text-ink", priceOff && TINT)}>{il?.unit_price_display ?? "—"}</td>
                  <td className={cn(num, "text-ink-2", priceOff && TINT)}>{pl?.unit_price_display ?? "—"}</td>
                  <td className={cn(num, "text-ink")}>{il?.amount_display ?? pl?.amount_display ?? "—"}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
