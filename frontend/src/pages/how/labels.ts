import type { Audience, CaseOutcome, StageStatus } from "@/types"

export const OUTCOME_STATUS: Record<CaseOutcome, StageStatus> = { Pass: "pass", Hold: "warn", Reject: "fail", Info: "info" }
export const OUTCOME_TONE = { Pass: "pass", Hold: "hold", Reject: "reject", Info: "info" } as const
export const AUDIENCE_LABEL: Record<Audience, string> = {
  Vendor: "Vendor",
  AP: "AP team",
  Procurement: "Procurement",
  Finance: "Finance",
}
