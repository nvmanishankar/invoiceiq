export type StageStatus = "pass" | "warn" | "fail" | "info"
export type Decision = "Approve" | "Hold" | "Reject"

export type Finding = {
  code: string
  label: string
  severity: "pass" | "hold" | "reject" | "info"
  message: string
  audience: string[]
  fraud?: boolean
}

export type Stage = {
  order: number
  name: string
  status: StageStatus
  message: string
  details: Record<string, unknown> & { findings?: Finding[] }
  duration_ms: number | null
  created_at?: string | null
}

export type DecisionInfo = {
  run_id: string
  decision: Decision | null
  status: string
  headline: string | null
  reasons: Omit<Finding, "fraud">[]
  fraud: boolean
  vendor_name: string | null
  po_id: string | null
  total_paise: number | null
  total_display: string | null
  due_date: string | null
}

export type Sample = {
  file: string
  story: string
  expected_decision: Decision
  expected_codes: string[]
  invoice_no?: string | null
  vendor_id?: string | null
  total_paise?: number | null
}

export type InvoiceLine = {
  line_no: number
  description: string
  qty: number | null
  unit: string | null
  unit_price_paise: number | null
  unit_price_display: string | null
  tax_rate: number | null
  amount_paise: number | null
  amount_display: string | null
  matched_po_line?: number | null
}

export type PoLine = InvoiceLine & {
  hsn_code?: string | null
  invoiced_qty_before: number
  remaining_qty_before: number
}

export type ComparisonRow = {
  invoice_line: InvoiceLine | null
  po_line: PoLine | null
  qty_diff: number | null
  unit_price_diff_paise: number | null
  unit_price_diff_display: string | null
}

export type PoView = {
  po_id: string
  vendor_name: string | null
  po_date: string | null
  status: string
  lines: PoLine[]
  total_paise: number
  total_display: string
  invoiced_before_paise: number
  invoiced_before_display: string
  remaining_before_paise: number
  remaining_before_display: string
  remaining_paise: number
  remaining_display: string
}

export type AlertGroups = {
  fraud: boolean
  vendor_suppressed: boolean
  by_audience: Record<string, { code: string; label: string; severity: string; message: string }[]>
}

export type RunDetail = {
  run_id: string
  file_name: string | null
  status: string
  decision: DecisionInfo | null
  invoice_no: string | null
  vendor_name: string | null
  po_id: string | null
  created_at: string | null
  finished_at: string | null
  stages: Stage[]
  findings: (Finding & { stage_order: number; stage_name: string })[]
  alert_groups: AlertGroups
  alerts: AlertRow[]
  reviews: ReviewEntry[]
  extraction: Extraction | null
  invoice: { invoice_no: string | null; invoice_date: string | null; total_paise: number | null; total_display: string | null }
  po: PoView | null
  comparison: ComparisonRow[]
  has_file: boolean
}

export type AlertStatus = "Drafted" | "Sent" | "Failed"

export type AlertRow = {
  alert_id: number
  run_id: string
  audience: string
  intended_for: string | null
  to_email: string
  subject: string
  body: string
  status: AlertStatus
  sent_at: string | null
  invoice_no: string | null
  run_status: string | null
}

export type FieldChange = {
  label?: string
  before: unknown
  after: unknown
  before_display?: string | null
  after_display?: string | null
}

export type ReviewEntry = {
  review_id: number
  reviewer: string | null
  action: string
  reason: string | null
  field_changes: Record<string, FieldChange> | null
  created_at: string | null
}

export type Confidence = "high" | "medium" | "low" | null

/** Stage 2 output as stored: money in rupees, dates ISO. */
export type Extraction = {
  vendor_name: string | null
  vendor_gstin: string | null
  invoice_number: string | null
  invoice_date: string | null
  po_reference: string | null
  currency: string | null
  subtotal: number | null
  cgst: number | null
  sgst: number | null
  igst: number | null
  total: number | null
  bank_account: string | null
  ifsc: string | null
  payment_terms_days: number | null
  confidence?: Partial<Record<string, Confidence>>
}

export type RunSummary = {
  run_id: string
  file_name: string | null
  status: string
  decision: Decision | null
  invoice_no: string | null
  vendor_name: string | null
  po_id: string | null
  total_paise: number | null
  total_display: string | null
  top_reason: string | null
  created_at: string | null
}

export type ReviewQueue = { count: number; runs: RunSummary[] }

export type ReviewAction =
  | { action: "confirm"; fields: Record<string, string | number | null> }
  | { action: "pick_po"; po_id: string }
  | { action: "override"; reason: string }
  | { action: "send_to_vendor"; reason: string; note?: string }
  | { action: "reject"; reason: string }

export type Money = { paise: number; display: string }

export type Stats = {
  generated_at: string
  kpis: {
    processed: number
    in_progress: number
    touchless: number
    touchless_rate: number | null
    approved: number
    held: number
    rejected: number
    waiting_on_vendor: number
    open_review: number
    money_protected: Money & { breakdown: (Money & { key: string; label: string; runs: number })[] }
    time_saved: { minutes: number; hours: number; minutes_per_invoice: number; assumption: string }
    avg_processing_seconds: number | null
  }
  today: { date: string; processed: number; touchless: number; held: number; rejected: number }
  series: {
    decisions_per_day: ({ date: string } & Record<Decision, number>)[]
    top_reasons: { code: string; label: string; title: string; count: number; hold: number; reject: number }[]
  }
  health: {
    low_confidence_runs: number
    low_confidence_share: number | null
    system_error_runs: number
    system_error_share: number | null
    llm_calls_per_run: number | null
    avg_stage_ms: number | null
  }
  vendors: { vendor_id: string; name: string; runs: number }[]
}

export type RunFilters = { status?: string; vendor?: string; q?: string }
