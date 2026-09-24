import type { ReactNode } from "react"
import { Link } from "react-router-dom"

import { DataTable } from "@/components/ds/DataTable"
import { FraudBanner } from "@/components/ds/FraudBanner"
import { CodeChip } from "@/components/ds/StatusChip"
import { day, inr, qty } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { Finding, Stage } from "@/types"
import { FRAUD_TITLE } from "./narration"

type Dict = Record<string, unknown>

const TONE = { pass: "pass", hold: "hold", reject: "reject", info: "info" } as const


function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mt-5 first:mt-0">
      <p className="label mb-2">{title}</p>
      {children}
    </div>
  )
}

export function FindingList({ findings }: { findings: Finding[] }) {
  if (!findings.length) return <p className="text-ink-3">No findings from this step.</p>
  return (
    <ul className="flex flex-col gap-3">
      {findings.map((f, i) => (
        <li key={`${f.code}-${i}`} className="flex gap-3">
          <CodeChip code={f.label ?? f.code} tone={TONE[f.severity] ?? "neutral"} />
          <div className="min-w-0">
            <p className="leading-relaxed text-ink">{f.message}</p>
            <p className="mt-1 font-mono text-[12px] text-ink-3">
              {f.audience.length ? `Tells ${f.audience.join(", ")}` : "No one needs to act"}
            </p>
          </div>
        </li>
      ))}
    </ul>
  )
}

const asArray = (v: unknown): Dict[] => (Array.isArray(v) ? (v.filter((x) => x && typeof x === "object") as Dict[]) : [])
const str = (v: unknown) => (v == null ? "—" : String(v))

function MatchPo({ d }: { d: Dict }) {
  const elimination = asArray(d.elimination)
  const scores = asArray(d.scores)
  const top = d.top as string | undefined
  return (
    <>
      {(d.printed != null || d.po_id != null) && (
        <Block title="Reference">
          <p className="text-ink">
            {d.printed ? <>Printed on the invoice: <span className="font-mono">{str(d.printed)}</span></> : "No PO reference printed."}
            {Array.isArray(d.tried) && d.tried.length > 0 && (
              <span className="text-ink-2"> Tried {(d.tried as string[]).join(", ")}.</span>
            )}
          </p>
        </Block>
      )}
      {elimination.length > 0 && (
        <Block title="Which POs could it be">
          <DataTable
            caption="PO elimination"
            rows={elimination}
            rowKey={(r) => str(r.po_id)}
            rowClassName={(r) => (r.eliminated_by == null ? "bg-approve-bg/60" : undefined)}
            columns={[
              { key: "po", head: "PO", cell: (r) => <span className="font-mono">{str(r.po_id)}</span> },
              { key: "by", head: "Ruled out by", cell: (r) => (r.eliminated_by == null ? <span className="text-approve">Still in</span> : str(r.eliminated_by)) },
              { key: "why", head: "Why", cell: (r) => <span className="text-ink-2">{str(r.reason)}</span> },
            ]}
          />
        </Block>
      )}
      {scores.length > 0 && (
        <Block title="Scores: lines out of 50, amount 30, date 20">
          <DataTable
            caption="PO scores"
            rows={scores}
            rowKey={(r) => str(r.po_id)}
            rowClassName={(r) => (r.po_id === top ? "font-medium" : undefined)}
            columns={[
              { key: "po", head: "PO", cell: (r) => <span className="font-mono">{str(r.po_id)}{r.po_id === top && <span className="ml-2 text-accent">best</span>}</span> },
              { key: "l", head: "Lines", align: "right", cell: (r) => str(r.lines) },
              { key: "a", head: "Amount", align: "right", cell: (r) => str(r.amount) },
              { key: "d", head: "Date", align: "right", cell: (r) => str(r.date) },
              { key: "t", head: "Total", align: "right", cell: (r) => <span className="text-ink">{typeof r.total === "number" ? r.total.toFixed(1) : str(r.total)}</span> },
            ]}
          />
        </Block>
      )}
      {typeof d.explanation === "string" && (
        <Block title="Why this PO">
          <p className="leading-relaxed text-ink">{d.explanation}</p>
        </Block>
      )}
    </>
  )
}

function Amounts({ d }: { d: Dict }) {
  const previous = asArray(d.previous_invoices)
  const lines = asArray(d.lines)
  return (
    <>
      <Block title="Balance">
        <dl className="grid grid-cols-3 gap-4">
          {[
            ["PO total", d.po_total_paise],
            ["Remaining before this invoice", d.remaining_paise],
            ["This invoice", d.invoice_total_paise],
          ].map(([k, v]) => (
            <div key={k as string}>
              <dt className="text-[13px] text-ink-3">{k as string}</dt>
              <dd className="num mt-0.5 text-[17px] text-ink">{inr(v as number | null)}</dd>
            </div>
          ))}
        </dl>
      </Block>
      <Block title="Earlier invoices on this PO">
        {previous.length ? (
          <DataTable
            caption="Earlier invoices on this PO"
            rows={previous}
            rowKey={(r) => str(r.run_id)}
            columns={[
              { key: "no", head: "Invoice", cell: (r) => <span className="font-mono">{str(r.invoice_no)}</span> },
              { key: "date", head: "Date", cell: (r) => day(r.invoice_date as string) },
              { key: "run", head: "Run", cell: (r) => <RunLink id={str(r.run_id)} /> },
              { key: "amt", head: "Amount", align: "right", cell: (r) => inr(r.total_paise as number) },
            ]}
          />
        ) : (
          <p className="text-ink-2">None. This is the first invoice against the PO.</p>
        )}
      </Block>
      {typeof d.lines === "string" && <Block title="Lines"><p className="text-ink-2">{d.lines}</p></Block>}
      {lines.length > 0 && (
        <Block title="Lines against the PO">
          <DataTable
            caption="Line checks"
            rows={lines}
            rowKey={(r, i) => `${str(r.po_line_no)}-${i}`}
            columns={[
              { key: "desc", head: "Invoice line", cell: (r) => str(r.invoice_line) },
              { key: "ord", head: "Ordered", align: "right", cell: (r) => qty(r.ordered as number) },
              { key: "already", head: "Billed before", align: "right", cell: (r) => qty(r.already as number) },
              {
                key: "now", head: "This invoice", align: "right",
                cell: (r) => qty(r.this_invoice as number),
                className: (r) =>
                  typeof r.ordered === "number" && (Number(r.already) || 0) + (Number(r.this_invoice) || 0) > r.ordered ? "bg-hold-bg text-hold" : undefined,
              },
              {
                key: "price", head: "Unit price (PO)", align: "right",
                cell: (r) => <>{inr(r.invoice_price_paise as number)} <span className="text-ink-3">({inr(r.po_price_paise as number)})</span></>,
              },
            ]}
          />
        </Block>
      )}
    </>
  )
}

function RunLink({ id }: { id: string }) {
  return (
    <Link to={`/process?run=${encodeURIComponent(id)}`} className="font-mono text-accent underline-offset-2 hover:underline">
      {id}
    </Link>
  )
}

function Duplicates({ d }: { d: Dict }) {
  const ids = Array.isArray(d.duplicate_of) ? (d.duplicate_of as string[]) : []
  return (
    <Block title="Duplicate check">
      <p className="text-ink">
        Compared against {str(d.checked)} earlier invoice(s).{" "}
        {ids.length ? (
          <>Same invoice as {ids.map((id, i) => <span key={id}>{i > 0 && ", "}<RunLink id={id} /></span>)}.</>
        ) : (
          "No duplicates."
        )}
      </p>
    </Block>
  )
}

const HIDDEN = new Set(["findings", "similarity_source"])

function humanise(k: string) {
  const s = k.replace(/_paise$/, "").replace(/_/g, " ")
  return s.charAt(0).toUpperCase() + s.slice(1)
}

function value(k: string, v: unknown): ReactNode {
  if (v == null) return <span className="text-ink-3">—</span>
  if (k.endsWith("_paise") && typeof v === "number") return <span className="num">{inr(v)}</span>
  if (typeof v === "boolean") return v ? "Yes" : "No"
  if (typeof v === "object") return <code className="font-mono text-[12px] break-all text-ink-2">{JSON.stringify(v)}</code>
  return String(v)
}

function Generic({ d }: { d: Dict }) {
  const entries = Object.entries(d).filter(([k]) => !HIDDEN.has(k))
  if (!entries.length) return null
  return (
    <Block title="Details">
      <dl className="grid grid-cols-[minmax(120px,max-content)_1fr] gap-x-6 gap-y-1.5">
        {entries.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-ink-3">{humanise(k)}</dt>
            <dd className="min-w-0 text-ink">{value(k, v)}</dd>
          </div>
        ))}
      </dl>
    </Block>
  )
}

export function StageEvidence({ stage }: { stage: Stage }) {
  const d = stage.details ?? {}
  const findings = d.findings ?? []
  const fraud = findings.find((f) => f.fraud)
  const specific =
    stage.name === "Match PO" ? <MatchPo d={d} />
    : stage.name === "Amounts and quantities" && d.po_total_paise !== undefined ? <Amounts d={d} />
    : stage.name === "Duplicates" ? <Duplicates d={d} />
    : <Generic d={d} />
  return (
    <div className={cn("flex flex-col gap-5 py-1")}>
      {fraud && (
        <FraudBanner title={FRAUD_TITLE[fraud.code] ?? "Finance must verify before paying"}>
          {fraud.message} No email goes to the vendor.
        </FraudBanner>
      )}
      <Block title="Findings">
        <FindingList findings={findings} />
      </Block>
      {specific}
    </div>
  )
}
