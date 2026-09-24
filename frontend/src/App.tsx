import type { ReactNode } from "react"
import { Navigate, Route, Routes } from "react-router-dom"

import { AppShell } from "@/components/AppShell"
import { MENU_ITEMS, NAV_ITEMS } from "@/nav"
import { Placeholder } from "@/pages/Placeholder"
import { ProcessPage } from "@/pages/process/ProcessPage"
import { Styleguide } from "@/pages/Styleguide"

const BUILT: Record<string, ReactNode> = {
  "/process": <ProcessPage />,
  "/styleguide": <Styleguide />,
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/process" replace />} />
        {[...NAV_ITEMS, ...MENU_ITEMS].map((item) => (
          <Route key={item.to} path={item.to} element={BUILT[item.to] ?? <Placeholder title={item.label} />} />
        ))}
        <Route path="*" element={<Placeholder title="Page not found" />} />
      </Route>
    </Routes>
  )
}
