import type { ReactNode } from "react"
import { Navigate, Route, Routes } from "react-router-dom"

import { AppShell } from "@/components/AppShell"
import { MENU_ITEMS, NAV_ITEMS } from "@/nav"
import { Placeholder } from "@/pages/Placeholder"
import { OutboxPage } from "@/pages/outbox/OutboxPage"
import { ProcessPage } from "@/pages/process/ProcessPage"
import { ReviewPage } from "@/pages/review/ReviewPage"
import { Styleguide } from "@/pages/Styleguide"
import { RoleProvider } from "@/components/RoleProvider"

const BUILT: Record<string, ReactNode> = {
  "/process": <ProcessPage />,
  "/review": <ReviewPage />,
  "/outbox": <OutboxPage />,
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
