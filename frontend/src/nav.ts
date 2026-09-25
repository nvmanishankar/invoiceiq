type NavItem = { to: string; label: string }

/** Centre links in the top bar. */
export const NAV_ITEMS: NavItem[] = [
  { to: "/process", label: "Process" },
  { to: "/review", label: "Review" },
  { to: "/dashboard", label: "Dashboard" },
  { to: "/pos", label: "Purchase orders" },
  { to: "/vendors", label: "Vendors" },
  { to: "/outbox", label: "Outbox" },
  { to: "/tests", label: "Tests" },
  { to: "/how-it-works", label: "How it works" },
]

/** Under the small menu on the right. */
export const MENU_ITEMS: NavItem[] = [
  { to: "/settings", label: "Settings" },
  { to: "/styleguide", label: "Styleguide" },
]
