import type {
  AlertRow,
  AppSettings,
  Catalogue,
  HowFacts,
  PoInput,
  PoRow,
  PoWalkthrough,
  ReviewAction,
  ReviewQueue,
  RunDetail,
  RunFilters,
  RunSummary,
  Sample,
  SettingsInput,
  Stats,
  VendorEmailPreview,
  VendorResponsePage,
  SuiteRun,
  TaxRate,
  VendorInput,
  VendorLoop,
  VendorRow,
} from "@/types"

export class ApiError extends Error {
  status: number
  /** Form problems by field (e.g. "gstin", "lines.0.qty"), when the server sends them. */
  errors: Record<string, string>
  /** Why a vendor response link can't be used: not_found / used / replaced / expired / closed / invalid / busy. */
  state: string | null
  constructor(status: number, message: string, errors: Record<string, string> = {}, state: string | null = null) {
    super(message)
    this.status = status
    this.errors = errors
    this.state = state
  }
}

async function check(res: Response): Promise<Response> {
  if (res.ok) return res
  let detail = `${res.status} ${res.statusText}`
  let errors: Record<string, string> = {}
  let state: string | null = null
  try {
    const body = await res.json()
    if (typeof body?.detail === "string") detail = body.detail
    if (body?.errors && typeof body.errors === "object") errors = body.errors
    if (typeof body?.state === "string") state = body.state
  } catch {
    // not JSON; keep the status line
  }
  throw new ApiError(res.status, detail, errors, state)
}

export async function getJson<T>(path: string): Promise<T> {
  const res = await check(await fetch(path))
  return res.json() as Promise<T>
}

async function postJson<T>(path: string, body?: unknown, headers: Record<string, string> = {}, method = "POST"): Promise<T> {
  const init: RequestInit = { method, headers: { ...headers } }
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json", ...headers }
    init.body = JSON.stringify(body)
  }
  const res = await check(await fetch(path, init))
  return res.json() as Promise<T>
}

export const fetchHealth = () => getJson<{ ok: boolean }>("/api/health")
export const getSamples = () => getJson<Sample[]>("/api/samples")
export const getRun = (runId: string) => getJson<RunDetail>(`/api/runs/${encodeURIComponent(runId)}`)
export const runFileUrl = (runId: string) => `/api/runs/${encodeURIComponent(runId)}/file`
export const runStreamUrl = (runId: string) => `/api/runs/${encodeURIComponent(runId)}/stream`

/** POST /api/runs with an uploaded PDF (multipart) or a sample name (JSON). */
export async function createRun(input: { file: File } | { sample_name: string }): Promise<{ run_id: string }> {
  let init: RequestInit
  if ("file" in input) {
    const form = new FormData()
    form.append("file", input.file)
    init = { method: "POST", body: form }
  } else {
    init = { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) }
  }
  const res = await check(await fetch("/api/runs", init))
  return res.json()
}

export const getReviewQueue = () => getJson<ReviewQueue>("/api/review-queue")

/** POST /api/runs/{id}/review. The role goes in X-Role; the server enforces who may do what. */
export const reviewRun = (runId: string, action: ReviewAction, role: string) =>
  postJson<{ run_id: string; action: string; status: string; resumed: boolean }>(
    `/api/runs/${encodeURIComponent(runId)}/review`,
    action,
    { "X-Role": role },
  )

/** The vendor email a reviewer would send: GET for the defaults, POST for chosen reasons and note. Nothing is sent. */
export const getVendorEmailPreview = (runId: string) =>
  getJson<VendorEmailPreview>(`/api/runs/${encodeURIComponent(runId)}/vendor-email-preview`)
export const previewVendorEmail = (runId: string, body: { reasons: string[]; note: string }) =>
  postJson<VendorEmailPreview>(`/api/runs/${encodeURIComponent(runId)}/vendor-email-preview`, body)

/** A corrected PDF for a held run: a new run that replaces it. The original becomes "superseded". */
export async function uploadCorrected(runId: string, file: File, role: string): Promise<{ run_id: string; replaces: string }> {
  const form = new FormData()
  form.append("file", file)
  const res = await check(await fetch(`/api/runs/${encodeURIComponent(runId)}/corrected`, {
    method: "POST", headers: { "X-Role": role }, body: form,
  }))
  return res.json()
}

/** The vendor's response link: public, no role. POST never says what was decided. */
export const getVendorResponse = (token: string) =>
  getJson<VendorResponsePage>(`/api/respond/${encodeURIComponent(token)}`)
export async function sendVendorResponse(token: string, file: File, message: string): Promise<{ message: string }> {
  const form = new FormData()
  form.append("file", file)
  if (message.trim()) form.append("message", message.trim())
  const res = await check(await fetch(`/api/respond/${encodeURIComponent(token)}`, { method: "POST", body: form }))
  return res.json()
}

export const getAlerts = () => getJson<AlertRow[]>("/api/alerts")
export const sendAlert = (alertId: number) => postJson<AlertRow>(`/api/alerts/${alertId}/send`)

/** Dashboard numbers. The viewer's UTC offset makes "today" and the daily bars follow their calendar. */
export const getStats = () => getJson<Stats>(`/api/stats?tz_offset=${-new Date().getTimezoneOffset()}`)

export function getRuns(filters: RunFilters = {}) {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) if (v) params.set(k, v)
  const qs = params.toString()
  return getJson<RunSummary[]>(`/api/runs${qs ? `?${qs}` : ""}`)
}

// --- Purchase orders, vendors, settings. Changes to POs and vendors carry the role; only Procurement may make them.

export const getPos = () => getJson<PoRow[]>("/api/pos")
export const getNextPoId = () => getJson<{ po_id: string; today: string }>("/api/pos/next-id")
export const createPo = (body: PoInput, role: string) => postJson<PoRow>("/api/pos", body, { "X-Role": role })
export const setPoStatus = (poId: string, status: "Open" | "Closed", role: string) =>
  postJson<PoRow>(`/api/pos/${encodeURIComponent(poId)}`, { status }, { "X-Role": role }, "PATCH")
export const getTaxRates = (on: string) => getJson<TaxRate[]>(`/api/tax-rates?country=IN&on=${encodeURIComponent(on)}`)

export const getVendors = () => getJson<VendorRow[]>("/api/vendors")
export const createVendor = (body: VendorInput, role: string) => postJson<VendorRow>("/api/vendors", body, { "X-Role": role })
export const setVendorStatus = (vendorId: string, status: "Active" | "Blocked", role: string) =>
  postJson<VendorRow>(`/api/vendors/${encodeURIComponent(vendorId)}`, { status }, { "X-Role": role }, "PATCH")

export const getSettings = () => getJson<AppSettings>("/api/settings")
/** Tolerance changes are Finance-only; the server checks the role. */
export const updateSettings = (body: SettingsInput, role: string) =>
  postJson<AppSettings>("/api/settings", body, { "X-Role": role }, "PATCH")
export const resetDemo = () => postJson<{ ok: boolean; message: string }>("/api/admin/reset", { confirm: "RESET" })

/** Every sample on a scratch copy of the data: nothing live is touched and no email is sent. */
export const runTestSuite = () => postJson<SuiteRun>("/api/admin/test-suite")

// --- How it works: read-only explainer data, straight from the code.
export const getCatalogue = () => getJson<Catalogue>("/api/how-it-works/cases")
export const getPoWalkthrough = () => getJson<PoWalkthrough>("/api/how-it-works/po-walkthrough")
export const getVendorLoop = () => getJson<VendorLoop>("/api/how-it-works/vendor-loop")
export const getHowFacts = () => getJson<HowFacts>("/api/how-it-works/facts")
export const getTaxHistory = () => getJson<TaxRate[]>("/api/how-it-works/tax-rates")
