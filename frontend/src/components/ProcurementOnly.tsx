import type { ReactNode } from "react"

import { canManagePurchasing, useRole } from "@/role"

/** Renders `children(disabled)` and, for any role but Procurement, the one-line reason underneath. */
export function ProcurementOnly({ action, children }: { action: string; children: (disabled: boolean) => ReactNode }) {
  const { role } = useRole()
  const allowed = canManagePurchasing(role)
  return (
    <div className="flex flex-col items-start gap-2">
      {children(!allowed)}
      {!allowed && (
        <p className="text-[13px] leading-snug text-ink-3">
          Only Procurement can {action}. The role is {role}; switch it at the top to continue.
        </p>
      )}
    </div>
  )
}
