import type { DecisionInfo, Stage } from "@/types"

export const GREETING =
  "Hi, I'm Iris, your AP associate. Drop an invoice and I'll check it against your POs, vendors and tax rules."

/** Stage names in pipeline order (backend/app/pipeline/runner.py STAGES). */
export const STAGE_NAMES = [
  "Read document",
  "Extract fields",
  "Completeness and maths",
  "Verify vendor",
  "Match PO",
  "Amounts and quantities",
  "Duplicates",
  "Tax",
  "Dates and terms",
]

const DOING: Record<string, string> = {
  "Read document": "Reading the invoice…",
  "Extract fields": "Pulling out the fields…",
  "Completeness and maths": "Checking the maths…",
  "Verify vendor": "Checking the vendor…",
  "Match PO": "Finding the PO…",
  "Amounts and quantities": "Comparing amounts…",
  Duplicates: "Looking for duplicates…",
  Tax: "Checking the tax…",
  "Dates and terms": "Working out the due date…",
}

function trim(s: string, max = 120): string {
  return s.length <= max ? s : `${s.slice(0, max - 1).trimEnd()}…`
}

export function doing(stageName: string): string {
  return DOING[stageName] ?? `${stageName}…`
}

/** One short line for the speech bubble. */
export function narrate(stages: Stage[], decision: DecisionInfo | null, running: boolean): string {
  if (decision?.decision) {
    const first = decision.reasons[0]?.message
    if (decision.fraud) return "These bank or tax details don't match what we have on file. Stopping for Finance."
    if (decision.decision === "Approve") return trim(`All checks pass. ${decision.headline ?? ""}`, 140)
    if (decision.decision === "Hold") return trim(`Holding this one. ${first ?? decision.headline ?? ""}`, 140)
    return trim(`Rejecting this one. ${first ?? decision.headline ?? ""}`, 140)
  }
  const last = [...stages].reverse().find((s) => s.order <= STAGE_NAMES.length)
  if (last) {
    if (last.name === "Read document" && /scan/i.test(last.message)) return "Reading the invoice… it's a scan, so I'm reading it visually."
    return trim(`${doing(last.name)} ${last.message}`)
  }
  return running ? "Opening the file…" : GREETING
}

/** Fraud banner titles by case code (design doc 4.6, 4.7). */
export const FRAUD_TITLE: Record<string, string> = {
  "4.6": "Finance must verify: GSTIN doesn't match the vendor on file",
  "4.7": "Finance must verify: bank account changed",
}
