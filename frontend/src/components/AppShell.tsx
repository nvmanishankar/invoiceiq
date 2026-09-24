import { useState } from "react"
import { NavLink, Outlet } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { FileText } from "lucide-react"

import { fetchHealth } from "@/api"
import { Badge } from "@/components/ui/badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { cn } from "@/lib/utils"
import { NAV_ITEMS } from "@/nav"

const ROLES = ["Procurement", "AP clerk", "Finance"] as const

export function AppShell() {
  const [role, setRole] = useState<string>("AP clerk")
  const reviewCount = 0 // wired to the review queue in a later phase

  return (
    <div className="flex min-h-svh bg-background">
      <aside className="flex w-60 shrink-0 flex-col border-r bg-sidebar">
        <div className="flex h-14 items-center gap-2 px-5">
          <FileText className="size-5 text-primary" />
          <span className="font-semibold tracking-tight">InvoiceIQ</span>
        </div>
        <nav className="flex flex-col gap-0.5 px-3 py-2">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                  isActive && "bg-sidebar-accent font-medium text-sidebar-accent-foreground",
                )
              }
            >
              <Icon className="size-4" />
              <span className="flex-1">{label}</span>
              {to === "/review" && <Badge variant="secondary">{reviewCount}</Badge>}
            </NavLink>
          ))}
        </nav>
        <HealthDot />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-end gap-3 border-b bg-card px-6">
          <span className="text-sm text-muted-foreground">Role</span>
          <Select value={role} onValueChange={setRole}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ROLES.map((r) => (
                <SelectItem key={r} value={r}>
                  {r}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </header>
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

function HealthDot() {
  const { isSuccess, isError } = useQuery({ queryKey: ["health"], queryFn: fetchHealth, refetchInterval: 30_000 })
  const label = isSuccess ? "API connected" : isError ? "API unreachable" : "Checking API…"
  return (
    <div className="mt-auto flex items-center gap-2 px-5 py-4 text-xs text-muted-foreground">
      <span
        className={cn(
          "size-2 rounded-full",
          isSuccess ? "bg-green-500" : isError ? "bg-red-500" : "bg-muted-foreground/40",
        )}
      />
      {label}
    </div>
  )
}
