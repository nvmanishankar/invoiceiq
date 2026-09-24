import { lazy, Suspense, type ReactNode } from "react"
import { Navigate, Route, Routes } from "react-router-dom"

import { AppShell } from "@/components/AppShell"
import { MENU_ITEMS, NAV_ITEMS } from "@/nav"
import { Placeholder } from "@/pages/Placeholder"
import { OutboxPage } from "@/pages/outbox/OutboxPage"
import { PosPage } from "@/pages/pos/PosPage"
import { ProcessPage } from "@/pages/process/ProcessPage"
import { ReviewPage } from "@/pages/review/ReviewPage"
import { SettingsPage } from "@/pages/settings/SettingsPage"
import { Styleguide } from "@/pages/Styleguide"
import { TestsPage } from "@/pages/tests/TestsPage"
import { VendorsPage } from "@/pages/vendors/VendorsPage"
import { RoleProvider } from "@/components/RoleProvider"

// Recharts is heavy; only the dashboard needs it.
const DashboardPage = lazy(() => import("@/pages/dashboard/DashboardPage").then((m) => ({ default: m.DashboardPage })))

const BUILT: Record<string, ReactNode> = {
  "/process": <ProcessPage />,
  "/review": <ReviewPage />,
  "/dashboard": <Suspense fallback={null}><DashboardPage /></Suspense>,
  "/pos": <PosPage />,
  "/vendors": <VendorsPage />,
  "/outbox": <OutboxPage />,
  "/tests": <TestsPage />,
  "/settings": <SettingsPage />,
  "/styleguide": <Styleguide />,
}

export default function App() {
  return (
    <RoleProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/process" replace />} />
          <Route path="/review/:runId" element={<ReviewPage />} />
          {[...NAV_ITEMS, ...MENU_ITEMS].map((item) => (
            <Route key={item.to} path={item.to} element={BUILT[item.to] ?? <Placeholder title={item.label} />} />
          ))}
          <Route path="*" element={<Placeholder title="Page not found" />} />
        </Route>
      </Routes>
    </RoleProvider>
  )
}
