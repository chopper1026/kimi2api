import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom"
import AppLayout from "@/components/layout/AppLayout"
import LoginPage from "@/pages/LoginPage"
import DashboardPage from "@/pages/DashboardPage"
import TokenPage from "@/pages/TokenPage"
import KeysPage from "@/pages/KeysPage"
import LogsPage from "@/pages/LogsPage"
import LogDetailPage from "@/pages/LogDetailPage"

function NotFoundPage() {
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-6">
      <div className="text-7xl font-bold text-muted-foreground/30">404</div>
      <p className="text-lg text-muted-foreground">页面不存在</p>
    </div>
  )
}

const router = createBrowserRouter([
  {
    path: "/admin/login",
    element: <LoginPage />,
  },
  {
    path: "/admin",
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/admin/dashboard" replace /> },
      { path: "dashboard", element: <DashboardPage /> },
      { path: "token", element: <TokenPage /> },
      { path: "keys", element: <KeysPage /> },
      { path: "logs", element: <LogsPage /> },
      { path: "logs/:requestId", element: <LogDetailPage /> },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
])

export default function App() {
  return <RouterProvider router={router} />
}
