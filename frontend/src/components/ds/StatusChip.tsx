import { cn } from "@/lib/utils"
import type { StageStatus } from "@/types"

const STYLE: Record<StageStatus, { word: string; cls: string }> = {
  pass: { word: "Pass", cls: "bg-approve-bg text-approve" },
  warn: { word: "Warn", cls: "bg-hold-bg text-hold" },
  fail: { word: "Fail", cls: "bg-reject-bg text-reject" },
  info: { word: "Info", cls: "bg-hover text-ink-2" },
}

export function StatusChip({ status, word, className }: { status: StageStatus; word?: string; className?: string }) {
  const s = STYLE[status] ?? STYLE.info
  return (
    <span className={cn("inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 font-mono text-[11px] font-medium tracking-[0.06em] uppercase", s.cls, className)}>
      <span aria-hidden className="size-1.5 rounded-[1px] bg-current" />
      {word ?? s.word}
    </span>
  )
}

const ALERT_TONE: Record<string, StageStatus> = { Sent: "pass", Drafted: "info", Failed: "fail" }

/** Email status: Sent / Drafted / Failed, in the stage chip's shape. */
export function AlertStatusChip({ status, className }: { status: string; className?: string }) {
  return <StatusChip status={ALERT_TONE[status] ?? "info"} word={status} className={className} />
}

/** Finding code in a mono chip, e.g. 6.5. */
export function CodeChip({ code, tone = "neutral" }: { code: string; tone?: "neutral" | "pass" | "hold" | "reject" | "info" }) {
  const cls = {
    neutral: "border-line bg-raised text-ink",
    info: "border-line bg-raised text-ink-2",
    pass: "border-approve/30 bg-approve-bg text-approve",
    hold: "border-hold/30 bg-hold-bg text-hold",
    reject: "border-reject/30 bg-reject-bg text-reject",
  }[tone]
  return <span className={cn("inline-flex h-6 shrink-0 items-center rounded-full border px-2 font-mono text-[11px] font-medium", cls)}>{code}</span>
}
