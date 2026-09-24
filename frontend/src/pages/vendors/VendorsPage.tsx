import { useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { getVendors, setVendorStatus } from "@/api"
import { ProcurementOnly } from "@/components/ProcurementOnly"
import { DataTable, type Column } from "@/components/ds/DataTable"
import { PillButton } from "@/components/ds/PillButton"
import { PillLink } from "@/components/ds/PillLink"
import { SectionTitle } from "@/components/ds/SectionTitle"
import { StatusChip } from "@/components/ds/StatusChip"
import { SplitContainer } from "@/components/ds/SplitContainer"
import { canManagePurchasing, useRole } from "@/role"
import type { VendorRow } from "@/types"
import { VendorForm } from "./VendorForm"

const FILTERS = ["All", "Active", "Blocked"] as const
type Filter = (typeof FILTERS)[number]

/** ?add opens the Add vendor form (the PO form links here). */
export function VendorsPage() {
  const [params, setParams] = useSearchParams()
  const adding = params.has("add")
  const [filter, setFilter] = useState<Filter>("All")
  const [added, setAdded] = useState<VendorRow | null>(null)
  const { role } = useRole()
  const allowed = canManagePurchasing(role)
  const qc = useQueryClient()
  const vendors = useQuery({ queryKey: ["vendors"], queryFn: getVendors })
  const status = useMutation({
    mutationFn: ({ v, to }: { v: VendorRow; to: "Active" | "Blocked" }) => setVendorStatus(v.vendor_id, to, role),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["vendors"] })
      qc.invalidateQueries({ queryKey: ["pos"] })
    },
  })

  const all = vendors.data ?? []
  const rows = filter === "All" ? all : all.filter((v) => v.status === filter)
  const count = (f: Filter) => (f === "All" ? all.length : all.filter((v) => v.status === f).length)

  const columns: Column<VendorRow>[] = [
    {
      key: "name",
      head: "Vendor",
      cell: (v) => (
        <div className="flex flex-col">
          <span className="text-ink">{v.name}</span>
          <span className="font-mono text-[12px] text-ink-3">{v.vendor_id}{v.open_pos ? ` · ${v.open_pos} open PO${v.open_pos === 1 ? "" : "s"}` : ""}</span>
        </div>
      ),
    },
    { key: "gstin", head: "GSTIN", cell: (v) => <span className="font-mono text-[13px]">{v.gstin ?? "—"}</span> },
    { key: "state", head: "State", cell: (v) => <span className="text-ink-2">{v.state ?? "—"}</span> },
    { key: "msme", head: "MSME", cell: (v) => <span className="text-ink-2">{v.msme ? "Yes" : "No"}</span> },
    { key: "status", head: "Status", cell: (v) => <StatusChip status={v.status === "Active" ? "pass" : "fail"} word={v.status} /> },
    {
      key: "bank",
      head: "Bank",
      cell: (v) => (
        <span className="flex flex-col">
          <span className="num font-mono text-[13px]" aria-label={v.bank_last4 ? `Account ending ${v.bank_last4}` : "No account"}>{v.bank_masked ?? "—"}</span>
          <span className="font-mono text-[11px] text-ink-3">{v.ifsc}</span>
        </span>
      ),
    },
    {
      key: "actions",
      head: <span className="sr-only">Actions</span>,
      align: "right",
      cell: (v) => {
        const busy = status.isPending && status.variables?.v.vendor_id === v.vendor_id
        return (
          <PillButton variant="secondary" className="h-9 px-4" disabled={!allowed || busy}
            title={allowed ? undefined : "Only Procurement can block or unblock vendors"}
            onClick={() => status.mutate({ v, to: v.status === "Active" ? "Blocked" : "Active" })}>
            {busy ? "Saving…" : v.status === "Active" ? "Block" : "Unblock"}
          </PillButton>
        )
      },
    },
  ]

  const rail = (
    <>
      <h1 className="text-h1">Vendors</h1>
      <p className="text-[15px] leading-relaxed text-ink-2">
        The approved vendor master. Invoices are matched to a vendor by GSTIN, and paid only into the account on file.
        A blocked vendor's invoices are rejected and no new POs can be raised for them.
      </p>
      <ProcurementOnly action="add or block vendors">
        {(disabled) => (
          <PillButton disabled={disabled || adding} onClick={() => { setAdded(null); setParams({ add: "" }) }}>Add vendor</PillButton>
        )}
      </ProcurementOnly>
      <nav aria-label="Filter vendors" className="flex flex-col gap-2.5">
        <p className="label mb-1">Show</p>
        {FILTERS.map((f, i) => (
          <PillLink key={f} dot={i + 3} active={!adding && filter === f} label={`${f} · ${count(f)}`}
            onClick={() => { setFilter(f); if (adding) setParams({}) }} />
        ))}
      </nav>
    </>
  )

  return (
    <SplitContainer rail={rail}>
      {adding ? (
        <VendorForm onCancel={() => setParams({})} onCreated={(v) => { setAdded(v); setFilter("All"); setParams({}) }} />
      ) : (
        <>
          <SectionTitle>{filter === "All" ? "Every vendor" : `${filter} vendors`}</SectionTitle>
          {added && (
            <div role="status" className="mt-6 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-card border border-approve/30 bg-approve-bg px-5 py-4 text-[15px] text-ink">
              <span>
                <span className="font-mono font-medium">{added.vendor_id}</span> {added.name} added ({added.state}).
              </span>
              <PillButton asChild variant="link">
                <Link to={`/pos?create=${encodeURIComponent(added.vendor_id)}`}>Create a PO for them</Link>
              </PillButton>
            </div>
          )}
          {status.error && <p role="alert" className="mt-4 text-[14px] text-reject">{status.error.message}</p>}
          {vendors.isError && <p role="alert" className="mt-4 text-hold">Couldn't load the vendors. Is the API running?</p>}
          {vendors.isSuccess && !rows.length && <p className="mt-4 text-ink-2">No vendors with this status.</p>}
          {rows.length > 0 && (
            <div className="mt-6">
              <DataTable caption="Vendors" columns={columns} rows={rows} rowKey={(v) => v.vendor_id} />
            </div>
          )}
        </>
      )}
    </SplitContainer>
  )
}
