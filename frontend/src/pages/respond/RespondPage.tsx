import { useRef, useState, type ReactNode } from "react"
import { useParams } from "react-router-dom"
import { useMutation, useQuery } from "@tanstack/react-query"

import { ApiError, getVendorResponse, sendVendorResponse } from "@/api"
import { MarkGlyph } from "@/components/brand/Mark"
import { inputCls } from "@/components/ds/Field"
import { PillButton } from "@/components/ds/PillButton"
import { day } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { VendorResponsePage } from "@/types"

const MAX_MB = 15

/** Why a link can't be used, in the vendor's words. The server's `state` picks the heading. */
const GONE: Record<string, string> = {
  not_found: "We couldn't find this link",
  used: "You've already sent a correction",
  replaced: "There's a newer link",
  expired: "This link has expired",
  closed: "Nothing more is needed",
}

/** The vendor's page from our email: the invoice, what to fix, and a box for the corrected PDF. No app shell. */
export function RespondPage() {
  const { token = "" } = useParams()
  const page = useQuery({ queryKey: ["respond", token], queryFn: () => getVendorResponse(token), retry: false })

  let content: ReactNode
  if (page.isLoading) content = <p className="text-ink-3">Loading…</p>
  else if (page.error) {
    const e = page.error
    const state = e instanceof ApiError ? e.state : null
    content = <Notice title={(state && GONE[state]) || "Something went wrong"}>{e.message}</Notice>
  } else if (page.data) content = <Respond token={token} page={page.data} />

  return (
    <div className="min-h-svh bg-canvas px-4 py-10 md:py-16">
      <main className="mx-auto flex max-w-2xl flex-col gap-8">
        <header className="flex items-center gap-3">
          <MarkGlyph size={18} />
          <p className="font-mono text-[12px] tracking-[0.06em] text-ink-3 uppercase">
            {page.data?.company_name ? `${page.data.company_name} · Accounts payable` : "Accounts payable"}
          </p>
        </header>
        {content}
      </main>
    </div>
  )
}

function Respond({ token, page }: { token: string; page: VendorResponsePage }) {
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [warning, setWarning] = useState<string | null>(null)
  const [message, setMessage] = useState("")
  const [dragging, setDragging] = useState(false)
  const send = useMutation({ mutationFn: () => sendVendorResponse(token, file!, message) })

  if (send.isSuccess) {
    return (
      <Notice title="Thank you">
        {send.data.message}. We'll be in touch if anything else is needed. You can close this page.
      </Notice>
    )
  }
  const gone = send.error instanceof ApiError && send.error.state && GONE[send.error.state]
  if (gone) return <Notice title={gone}>{send.error!.message}</Notice>

  const take = (files: FileList | null) => {
    const f = files?.[0]
    if (!f) return
    if (f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".pdf")) {
      setWarning(`${f.name} isn't a PDF.`)
      return
    }
    if (f.size > MAX_MB * 1024 * 1024) {
      setWarning(`${f.name} is larger than ${MAX_MB} MB.`)
      return
    }
    setWarning(null)
    setFile(f)
  }
  const tooLong = message.length > page.message_max

  return (
    <>
      <div className="flex flex-col gap-3">
        <h1 className="text-h1">Please send a corrected invoice</h1>
        <p className="max-w-prose leading-relaxed text-ink-2">
          Hello {page.vendor_name}. We can't process the invoice below yet. Upload a corrected PDF here and we'll check
          it again.
        </p>
      </div>

      <section aria-label="The invoice" className="rounded-card border border-line bg-raised p-6">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
          <Fact label="Invoice">{page.invoice_no ?? "No number"}</Fact>
          <Fact label="Date">{page.invoice_date ? day(page.invoice_date) : "No date"}</Fact>
          <Fact label="Total">{page.total_display ?? "—"}</Fact>
          <Fact label="PO">{page.po_id ?? "—"}</Fact>
        </dl>
        {page.issues.length > 0 && (
          <div className="mt-6 border-t border-line pt-5">
            <p className="label mb-3">What needs correcting</p>
            <ol className="flex list-decimal flex-col gap-2 pl-5 leading-relaxed text-ink marker:font-mono marker:text-ink-3">
              {page.issues.map((m) => <li key={m}>{m}</li>)}
            </ol>
          </div>
        )}
      </section>

      <form className="flex flex-col gap-5" onSubmit={(e) => { e.preventDefault(); if (file && !tooLong) send.mutate() }}>
        <div
          role="button"
          tabIndex={0}
          aria-label="Choose the corrected invoice PDF"
          onClick={() => input.current?.click()}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.current?.click() } }}
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); take(e.dataTransfer.files) }}
          className={cn(
            "flex cursor-pointer flex-col items-center gap-2 rounded-card border border-dashed bg-raised px-6 py-10 text-center transition-colors",
            dragging ? "border-accent" : "border-line hover:border-ink-3",
          )}
        >
          {file ? (
            <>
              <span className="max-w-full truncate font-mono text-[14px] text-ink">{file.name}</span>
              <span className="text-[13px] text-ink-3">Click to choose a different file</span>
            </>
          ) : (
            <>
              <span className="text-ink">Drop the corrected PDF here, or click to choose it</span>
              <span className="text-[13px] text-ink-3">PDF, up to {MAX_MB} MB</span>
            </>
          )}
        </div>
        <input ref={input} type="file" accept="application/pdf,.pdf" className="sr-only" tabIndex={-1}
          aria-hidden onChange={(e) => { take(e.target.files); e.target.value = "" }} />
        {warning && <p role="alert" className="text-[14px] text-hold">{warning}</p>}

        <label className="flex flex-col gap-1.5">
          <span className="label">Message (optional)</span>
          <textarea value={message} onChange={(e) => setMessage(e.target.value)} rows={3}
            placeholder="Anything we should know about the correction."
            className={cn(inputCls, "h-auto py-3 leading-relaxed")} />
          <span className={cn("text-right font-mono text-[12px]", tooLong ? "text-reject" : "text-ink-3")}>
            {message.length.toLocaleString("en-IN")} / {page.message_max.toLocaleString("en-IN")}
          </span>
        </label>

        {send.error && <p role="alert" className="text-[14px] text-hold">{send.error.message}</p>}
        <div className="flex flex-wrap items-center gap-4">
          <PillButton type="submit" disabled={!file || tooLong || send.isPending}>
            {send.isPending ? "Sending…" : "Send corrected invoice"}
          </PillButton>
          <span className="text-[13px] text-ink-3">This link works until {page.expires_on}.</span>
        </div>
      </form>
      <p className="text-[13px] leading-relaxed text-ink-3">You can also reply to our email with the PDF attached.</p>
    </>
  )
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="label mb-1">{label}</dt>
      <dd className="num truncate font-mono text-[14px] text-ink">{children}</dd>
    </div>
  )
}

function Notice({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section role="status" className="flex flex-col gap-3 rounded-card border border-line bg-raised p-6">
      <h1 className="text-h2">{title}</h1>
      <p className="max-w-prose leading-relaxed text-ink-2">{children}</p>
    </section>
  )
}
