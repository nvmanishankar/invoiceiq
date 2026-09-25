import { useState } from "react"

import { cn } from "@/lib/utils"
import { ROLES, useRole, type Role } from "@/role"
import type { HowFacts, Permission } from "@/types"
import { Section, Segmented } from "./shared"

const RULE_ROLE: Record<Permission["rule"], Role | null> = { anyone: null, procurement: "Procurement", finance: "Finance" }

function allowed(p: Permission, role: Role): boolean {
  const only = RULE_ROLE[p.rule]
  return only === null || only === role
}

function allowedOnFraud(p: Permission, role: Role): boolean {
  return p.fraud === "finance" && role === "Finance"
}

export function RolesSection({ facts }: { facts: HowFacts | undefined }) {
  const current = useRole().role
  const [role, setRole] = useState<Role>(current)
  const perms = facts?.permissions ?? []
  const areas = [...new Set(perms.map((p) => p.area))]
  const n = perms.filter((p) => allowed(p, role)).length

  return (
    <Section
      id="roles"
      kicker="11 · Roles"
      title="Who can do what"
      lede="Three roles, picked in the top bar. The people who approve invoices must not also control the POs and vendors they're paid against: that's segregation of duties. Pick a role to see every action the server guards."
    >
      <div className="flex flex-wrap items-center gap-4">
        <Segmented label="Role" value={role} onChange={setRole} options={ROLES.map((r) => ({ value: r, label: r }))} />
        {facts && <p className="font-mono text-[13px] text-ink-2" aria-live="polite">{n} of {perms.length} actions allowed</p>}
      </div>

      {!facts ? <div className="mt-5 h-96 animate-pulse rounded-card bg-hover" aria-busy /> : (
        <div className="mt-5 overflow-hidden rounded-card border border-line bg-raised">
          {areas.map((area) => (
            <div key={area} className="border-t border-line first:border-t-0">
              <p className="label bg-surface px-5 py-2">{area}</p>
              <ul>
                {perms.filter((p) => p.area === area).map((p) => {
                  const ok = allowed(p, role)
                  return (
                    <li key={p.key} className="grid gap-x-5 gap-y-1.5 border-t border-line px-5 py-3.5 md:grid-cols-[220px_110px_minmax(0,1fr)]">
                      <span className="text-[15px] text-ink">{p.action}</span>
                      <span><Verdict ok={ok} /></span>
                      <span className="text-[14px] leading-relaxed text-ink-2">
                        {ok ? p.why : `Only ${RULE_ROLE[p.rule]} can do this. ${p.why}`}
                        {p.fraud && (
                          <span className="mt-1.5 flex flex-wrap items-center gap-2">
                            <span className="font-mono text-[11px] font-medium tracking-[0.06em] text-reject uppercase">Fraud hold</span>
                            <Verdict ok={allowedOnFraud(p, role)} small />
                            <span>{p.fraud_why}</span>
                          </span>
                        )}
                      </span>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </div>
      )}

      <div className="mt-5 grid gap-3 md:grid-cols-2">
        <div className="rounded-card bg-bubble px-5 py-4">
          <p className="label">How it's enforced</p>
          <p className="mt-1.5 font-mono text-[13px] leading-[1.6] text-ink">
            The role goes with every request, and the server checks it: a blocked action is refused even if someone calls
            the API directly. No role, or an unknown one, counts as AP clerk, never as something stronger.
          </p>
        </div>
        <div className="rounded-card bg-bubble px-5 py-4">
          <p className="label">Not yet</p>
          <p className="mt-1.5 font-mono text-[13px] leading-[1.6] text-ink">
            The role is a selector, not a login. Review actions aren't limited by role except on fraud holds, and there
            are no approval limits by amount. Both are on the roadmap below.
          </p>
        </div>
      </div>
    </Section>
  )
}

function Verdict({ ok, small }: { ok: boolean; small?: boolean }) {
  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 rounded-full font-mono font-medium tracking-[0.06em] uppercase",
      small ? "h-5 px-2 text-[10px]" : "h-6 px-2.5 text-[11px]",
      ok ? "bg-approve-bg text-approve" : "bg-reject-bg text-reject",
    )}>
      <span aria-hidden>{ok ? "✓" : "×"}</span>
      {ok ? "Allowed" : "Blocked"}
    </span>
  )
}
