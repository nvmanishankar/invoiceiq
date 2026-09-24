import type { Decision } from "@/types"

export const DECISION_WORD: Record<Decision, string> = { Approve: "Approved", Hold: "On hold", Reject: "Rejected" }
export const DECISION_TONE: Record<Decision, { fg: string; bg: string; text: string }> = {
  Approve: { fg: "var(--approve)", bg: "var(--approve-bg)", text: "text-approve" },
  Hold: { fg: "var(--hold)", bg: "var(--hold-bg)", text: "text-hold" },
  Reject: { fg: "var(--reject)", bg: "var(--reject-bg)", text: "text-reject" },
}
