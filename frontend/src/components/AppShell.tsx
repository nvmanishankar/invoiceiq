import { useState } from "react"
import { Link, NavLink, Outlet, useLocation } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { motion, useReducedMotion } from "motion/react"
import { DropdownMenu } from "radix-ui"

import { fetchHealth } from "@/api"
import { DotMatrix } from "@/components/brand/DotMatrix"
import { Mark } from "@/components/brand/Mark"
import { PillButton } from "@/components/ds/PillButton"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useHeadroom } from "@/hooks/useHeadroom"
import { pageEnter } from "@/lib/motion"
import { cn } from "@/lib/utils"
import { MENU_ITEMS, NAV_ITEMS } from "@/nav"

const ROLES = ["Procurement", "AP clerk", "Finance"] as const

export function AppShell() {
  const [role, setRole] = useState<string>("AP clerk")
  const shown = useHeadroom()
  const reduce = useReducedMotion()
  const { pathname } = useLocation()

  return (
    <div className="flex min-h-svh flex-col bg-canvas">
      <header
        className={cn(
          "sticky top-0 z-40 border-b border-line bg-canvas/90 backdrop-blur-md transition-transform duration-[250ms] ease-out",
          !shown && "-translate-y-full",
        )}
      >
        <div className="mx-auto flex h-16 max-w-[1440px] items-center gap-6 px-4 md:px-8">
          <Link to="/process" aria-label="InvoiceIQ home" className="shrink-0 rounded-md">
            <Mark />
          </Link>
          <nav aria-label="Main" className="mx-auto hidden items-center gap-1 lg:flex">
            {NAV_ITEMS.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  cn(
                    "rounded-full px-3 py-1.5 text-[14px] transition-colors duration-200",
                    isActive ? "bg-raised text-ink shadow-[inset_0_0_0_1px_var(--line)]" : "text-ink-2 hover:text-ink",
                  )
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2 lg:ml-0">
            <Select value={role} onValueChange={setRole}>
              <SelectTrigger
                aria-label="Role"
                className="h-11! rounded-full! border-line bg-raised pr-3 pl-4 font-mono text-[13px] text-ink hover:border-ink"
              >
                <span className="text-ink-3">Role</span>
                <SelectValue />
              </SelectTrigger>
              <SelectContent position="popper" sideOffset={6} className="rounded-input shadow-float">
                {ROLES.map((r) => (
                  <SelectItem key={r} value={r}>
                    {r}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <PillButton asChild className="hidden md:inline-flex">
              <Link to="/process">Process invoice</Link>
            </PillButton>
            <MoreMenu />
          </div>
        </div>
        <nav aria-label="Main" className="flex gap-1 overflow-x-auto px-4 pb-2 lg:hidden">
          {NAV_ITEMS.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn("shrink-0 rounded-full px-3 py-1 text-[13px]", isActive ? "bg-raised text-ink" : "text-ink-2")
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
      </header>

      <motion.main
        key={pathname}
        variants={pageEnter}
        initial={reduce ? false : "initial"}
        animate="animate"
        className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-6 md:px-8 md:py-8"
      >
        <Outlet />
      </motion.main>

      <footer className="mt-10 border-t border-line">
        <div className="mx-auto max-w-[1440px] px-4 md:px-8">
          <DotMatrix text="InvoiceIQ" color="var(--accent)" height={150} className="text-accent" />
          <div className="flex items-center justify-between pb-6 text-[13px] text-ink-3">
            <span>AI reads, rules decide.</span>
            <HealthDot />
          </div>
        </div>
      </footer>
    </div>
  )
}

function MoreMenu() {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger
        aria-label="More"
        className="grid size-11 place-items-center rounded-full border border-line bg-raised text-ink transition-colors hover:border-ink"
      >
        <svg viewBox="0 0 7 1" width="14" height="2" aria-hidden shapeRendering="crispEdges">
          <rect x="0" width="1" height="1" fill="currentColor" />
          <rect x="3" width="1" height="1" fill="currentColor" />
          <rect x="6" width="1" height="1" fill="currentColor" />
        </svg>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={8}
          className="z-50 min-w-48 rounded-input border border-line bg-raised p-1.5 shadow-float"
        >
          {MENU_ITEMS.map(({ to, label }) => (
            <DropdownMenu.Item key={to} asChild>
              <Link to={to} className="block rounded-[10px] px-3 py-2 text-[14px] text-ink outline-none data-highlighted:bg-hover">
                {label}
              </Link>
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}

function HealthDot() {
  const { isSuccess, isError } = useQuery({ queryKey: ["health"], queryFn: fetchHealth, refetchInterval: 30_000 })
  const label = isSuccess ? "API connected" : isError ? "API unreachable" : "Checking API…"
  return (
    <span className="flex items-center gap-2 font-mono text-[12px]">
      <span
        aria-hidden
        className={cn("size-2 rounded-[1px]", isSuccess ? "bg-approve" : isError ? "bg-reject" : "bg-ink-3")}
      />
      {label}
    </span>
  )
}
