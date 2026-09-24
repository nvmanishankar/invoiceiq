import { Link } from "react-router-dom"
import { useMutation, useQueryClient } from "@tanstack/react-query"

import { setPoStatus } from "@/api"
import { DataTable, type Column } from "@/components/ds/DataTable"
import { PillButton } from "@/components/ds/PillButton"
import { StatusChip } from "@/components/ds/StatusChip"
import { DECISION_WORD } from "@/lib/decision"
import { day, inr, qty } from "@/lib/format"
import { cn } from "@/lib/utils"
import { canManagePurchasing, useRole } from "@/role"
import type { BilledInvoice, Decision, PoRow, PoStatus, StageStatus } from "@/types"
import { TAX_TYPE_WORDS } from "./calc"

const PO_TONE: Record<PoStatus, StageStatus> = { Open: "pass", Closed: "info", Cancelled: "fail" }
const DECISION_CHIP: Record<Decision, StageStatus> = { Approve: "pass", Hold: "warn", Reject: "fail" }

/** The PO register: one row per PO, a remaining-balance bar, and the lines and invoices underneath when opened. */
export function PoTable({ rows, openIds, onToggle }: { rows: PoRow[]; openIds: Set<string>; onToggle: (id: string) => void }) {
  const { role } = useRole()
  const allowed = canManagePurchasing(role)
  const qc = useQueryClient()
  const status = useMutation({
    mutationFn: ({ po, to }: { po: PoRow; to: "Open" | "Closed" }) => setPoStatus(po.po_id, to, role),
    onSettled: () => qc.invalidateQueries({ queryKey: ["pos"] }),
  })

  const columns: Column<PoRow>[] = [
    {
      key: "po",
      head: "PO",
      cell: (p) => (
        <button type="button" aria-expanded={openIds.has(p.po_id)} aria-controls={`po-${p.po_id}`}
          onClick={() => onToggle(p.po_id)} className="flex items-start gap-3 rounded-sm text-left">
          <span aria-hidden className={cn("mt-0.5 font-mono text-ink-3 transition-transform duration-200", openIds.has(p.po_id) && "rotate-45")}>+</span>
          <span className="flex flex-col">
            <span className="font-mono text-[13px] font-medium whitespace-nowrap text-ink">{p.po_id}</span>
            <span className="text-[12px] text-ink-3">{day(p.po_date)}</span>
          </span>
        </button>
      ),
    },
    {
      key: "vendor",
      head: "Vendor",
      cell: (p) => (
        <div className="flex flex-col">
          <span className="text-ink">{p.vendor_name}</span>
          <span className="text-[12px] text-ink-3">
            {[p.department, `Net ${p.payment_terms_days}`, TAX_TYPE_WORDS[p.tax_type]].filter(Boolean).join(" · ")}
          </span>
        </div>
      ),
    },
    { key: "status", head: "Status", cell: (p) => <StatusChip status={PO_TONE[p.status]} word={p.status} /> },
    { key: "total", head: "Total", align: "right", cell: (p) => p.total_display },
    { key: "balance", head: "Remaining", cell: (p) => <BalanceBar po={p} /> },
    {
      key: "actions",
      head: <span className="sr-only">Actions</span>,
      align: "right",
      cell: (p) => {
        if (p.status === "Cancelled") return null
        const to = p.status === "Open" ? "Closed" : "Open"
        const busy = status.isPending && status.variables?.po.po_id === p.po_id
        return (
          <PillButton variant="secondary" className="h-9 px-4" disabled={!allowed || busy}
            title={allowed ? undefined : "Only Procurement can close or reopen POs"}
            onClick={() => status.mutate({ po: p, to })}>
            {busy ? "Saving…" : p.status === "Open" ? "Close" : "Reopen"}
          </PillButton>
        )
      },
    },
  ]

  return (
    <>
      {status.error && <p role="alert" className="mb-4 text-[14px] text-reject">{status.error.message}</p>}
      <DataTable caption="Purchase orders" columns={columns} rows={rows} rowKey={(p) => p.po_id}
        renderExpanded={(p) => (openIds.has(p.po_id) ? <PoDetail po={p} /> : null)} />
    </>
  )
}

/** Billed (ink) and still available (blue) out of the PO total. */
function BalanceBar({ po }: { po: PoRow }) {
  const total = Math.max(po.total_paise, 1)
  const billed = Math.min(Math.max(po.invoiced_paise / total, 0), 1) * 100
  const open = po.status === "Open"
  return (
    <div className="w-44">
      <div className="flex items-baseline justify-between gap-2">
        <span className={cn("num text-[14px]", po.remaining_paise < 0 ? "text-reject" : "text-ink")}>{po.remaining_display}</span>
        <span className="num text-[12px] text-ink-3">{Math.round(100 - billed)}% left</span>
      </div>
      <div role="img" aria-label={`${po.invoiced_display} billed of ${po.total_display}; ${po.remaining_display} left`}
        className="mt-1.5 flex h-2 overflow-hidden rounded-full bg-hover">
        <div className="bg-ink" style={{ width: `${billed}%` }} />
        <div className={open ? "bg-accent" : "bg-ink-3/40"} style={{ width: `${100 - billed}%` }} />
      </div>
      <p className="mt-1 text-[12px] text-ink-3">{po.invoiced_display} billed</p>
    </div>
  )
}

function PoDetail({ po }: { po: PoRow }) {
  const split = po.tax_type === "CGST+SGST"
    ? `CGST ${inr(po.cgst_paise)} + SGST ${inr(po.sgst_paise)}`
    : po.tax_type === "IGST" ? `IGST ${inr(po.igst_paise)}` : "No GST from the vendor"
  return (
    <div id={`po-${po.po_id}`} className="grid gap-6 pl-7 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div>
        <p className="label mb-2">Ordered</p>
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-line text-left text-ink-3">
              <th scope="col" className="py-1.5 pr-3 font-normal">Item</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-normal">Qty</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-normal">Invoiced</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-normal">Unit price</th>
              <th scope="col" className="py-1.5 text-right font-normal">GST</th>
            </tr>
          </thead>
          <tbody>
            {po.lines.map((l) => (
              <tr key={l.line_no} className="border-b border-line last:border-b-0">
                <td className="py-2 pr-3 text-ink">
                  {l.description}
                  {l.hsn_code && <span className="ml-2 font-mono text-[11px] text-ink-3">HSN {l.hsn_code}</span>}
                </td>
                <td className="num py-2 pr-3 text-right">{qty(l.qty)} {l.unit}</td>
                <td className={cn("num py-2 pr-3 text-right", l.invoiced_qty > l.qty ? "text-reject" : "text-ink-2")}>{qty(l.invoiced_qty)}</td>
                <td className="num py-2 pr-3 text-right">{l.unit_price_display}</td>
                <td className="num py-2 text-right">{l.tax_rate}%</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="num mt-3 text-[13px] text-ink-2">
          Subtotal {po.subtotal_display} · {split} · <span className="font-medium text-ink">Total {po.total_display}</span>
        </p>
        <p className="mt-1 text-[12px] text-ink-3">
          {po.vendor_gstin && <span className="font-mono">{po.vendor_gstin}</span>} {po.vendor_state && `· ${po.vendor_state}`}
          {po.created_by && ` · raised by ${po.created_by}`}
        </p>
      </div>
      <div>
        <p className="label mb-2">Invoices billed against it</p>
        {po.invoices.length === 0 ? (
          <p className="text-[13px] text-ink-2">None yet. Only approved invoices use up the balance.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-line">
            {po.invoices.map((i) => <BilledRow key={i.run_id} inv={i} />)}
          </ul>
        )}
      </div>
    </div>
  )
}

function BilledRow({ inv }: { inv: BilledInvoice }) {
  const name = inv.invoice_no ?? inv.run_id
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-[13px]">
      {inv.is_seed ? (
        <span className="font-mono text-ink">{name}</span>
      ) : (
        <Link to={`/process?run=${encodeURIComponent(inv.run_id)}`} className="font-mono text-accent underline-offset-2 hover:underline">{name}</Link>
      )}
      <span className="text-ink-3">{day(inv.invoice_date)}</span>
      {inv.decision && <StatusChip status={DECISION_CHIP[inv.decision]} word={DECISION_WORD[inv.decision]} />}
      <span className="num ml-auto text-ink">{inv.total_display ?? "—"}</span>
      <span className="basis-full text-[12px] text-ink-3">
        {inv.is_seed ? "Approved before InvoiceIQ · " : ""}
        {inv.counts_against_po ? "Uses up the balance" : "Not counted: only approved invoices use up the balance"}
      </span>
    </li>
  )
}
