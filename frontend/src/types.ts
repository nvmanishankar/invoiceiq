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
  stages: Stage[]
  findings: (Finding & { stage_order: number; stage_name: string })[]
  alert_groups: AlertGroups
  alerts: { alert_id: number; audience: string; intended_for: string; subject: string; status: string }[]
  po: PoView | null
  comparison: ComparisonRow[]
  has_file: boolean
}
