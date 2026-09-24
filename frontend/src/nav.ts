import {
  FlaskConical,
  Inbox,
  LayoutDashboard,
  Mail,
  Package,
  ScanLine,
  Settings,
  Users,
  type LucideIcon,
} from "lucide-react"

type NavItem = { to: string; label: string; icon: LucideIcon }

export const NAV_ITEMS: NavItem[] = [
  { to: "/process", label: "Process", icon: ScanLine },
  { to: "/review", label: "Review", icon: Inbox },
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/pos", label: "Purchase orders", icon: Package },
  { to: "/vendors", label: "Vendors", icon: Users },
  { to: "/outbox", label: "Outbox", icon: Mail },
  { to: "/tests", label: "Tests", icon: FlaskConical },
  { to: "/settings", label: "Settings", icon: Settings },
]
