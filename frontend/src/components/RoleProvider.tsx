import { useState, type ReactNode } from "react"

import { DEFAULT_ROLE, ROLES, RoleContext, type Role } from "@/role"

const KEY = "invoiceiq.role"

function stored(): Role {
  try {
    const v = localStorage.getItem(KEY)
    return (ROLES as readonly string[]).includes(v ?? "") ? (v as Role) : DEFAULT_ROLE
  } catch {
    return DEFAULT_ROLE
  }
}

/** Holds the role chosen in the top bar and remembers it in this browser. */
export function RoleProvider({ children }: { children: ReactNode }) {
  const [role, set] = useState<Role>(stored)
  const setRole = (r: Role) => {
    set(r)
    try {
      localStorage.setItem(KEY, r)
    } catch {
      // private window: the role just isn't remembered
    }
  }
  return <RoleContext.Provider value={{ role, setRole }}>{children}</RoleContext.Provider>
}
