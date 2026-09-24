import { Navigate, Route, Routes } from "react-router-dom"

import { AppShell } from "@/components/AppShell"
import { NAV_ITEMS } from "@/nav"
import { Placeholder } from "@/pages/Placeholder"

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/process" replace />} />
        {NAV_ITEMS.map((item) => (
          <Route key={item.to} path={item.to} element={<Placeholder title={item.label} />} />
        ))}
        <Route path="*" element={<Placeholder title="Page not found" />} />
      </Route>
    </Routes>
  )
}
