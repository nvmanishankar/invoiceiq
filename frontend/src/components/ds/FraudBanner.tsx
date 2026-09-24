import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

/** Red banner with a dithered border. Fraud findings (4.6, 4.7) only. */
export function FraudBanner({ title, children, className }: { title: ReactNode; children?: ReactNode; className?: string }) {
  return (
    <div role="alert" className={cn("relative overflow-hidden rounded-card bg-reject-bg p-[5px] text-reject", className)}>
      <div aria-hidden className="dither absolute inset-0 opacity-70" />
      <div className="relative rounded-[16px] bg-reject-bg px-5 py-4">
        <p className="font-mono text-[13px] font-semibold tracking-[0.06em] uppercase">{title}</p>
        {children && <div className="mt-1.5 text-[15px] leading-relaxed text-ink">{children}</div>}
      </div>
    </div>
  )
}
