import type { RunDetail, Sample } from "@/types"

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function check(res: Response): Promise<Response> {
  if (res.ok) return res
  let detail = `${res.status} ${res.statusText}`
  try {
    const body = await res.json()
    if (typeof body?.detail === "string") detail = body.detail
  } catch {
    // not JSON; keep the status line
  }
  throw new ApiError(res.status, detail)
}

export async function getJson<T>(path: string): Promise<T> {
  const res = await check(await fetch(path))
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
