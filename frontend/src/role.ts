import { createContext, useContext } from "react"

export const ROLES = ["Procurement", "AP clerk", "Finance"] as const
export type Role = (typeof ROLES)[number]
export const DEFAULT_ROLE: Role = "AP clerk"

export const RoleContext = createContext<{ role: Role; setRole: (r: Role) => void }>({
  role: DEFAULT_ROLE,
  setRole: () => {},
})

/** The top-bar role. Sent as X-Role on review requests; the server decides what each role may do. */
export const useRole = () => useContext(RoleContext)

/** Segregation of duties: only Procurement raises POs and manages vendors. The server enforces it too. */
export const canManagePurchasing = (role: Role) => role === "Procurement"

/** Tolerance is a financial control: only Finance changes it. The server enforces it too. */
export const canChangeTolerance = (role: Role) => role === "Finance"
