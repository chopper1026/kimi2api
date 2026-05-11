import { NavLink, Outlet, useNavigate, useLocation } from "react-router-dom"
import {
  LayoutDashboard,
  Key,
  ShieldCheck,
  ClipboardList,
  LogOut,
  ChevronDown,
  User,
} from "lucide-react"
import { useAuth } from "@/hooks/use-auth"
import { useState, useRef, useEffect } from "react"

const navItems = [
  { to: "/admin/dashboard", label: "概览", icon: LayoutDashboard },
  { to: "/admin/token", label: "授权管理", icon: ShieldCheck },
  { to: "/admin/keys", label: "API Keys", icon: Key },
  { to: "/admin/logs", label: "请求日志", icon: ClipboardList },
]

const pageTitles: Record<string, string> = {
  "/admin/dashboard": "概览",
  "/admin/token": "授权管理",
  "/admin/keys": "API Keys",
  "/admin/logs": "请求日志",
}

function UserMenu({ onLogout }: { onLogout: () => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [open])

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-foreground transition-colors hover:bg-accent"
      >
        <div className="flex size-7 items-center justify-center rounded-full bg-primary/10 text-primary">
          <User className="size-3.5" />
        </div>
        <span className="hidden sm:inline">Admin</span>
        <ChevronDown className="size-3.5 text-muted-foreground" />
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-1 min-w-[160px] overflow-hidden rounded-lg border border-border bg-popover py-1 shadow-lg">
          <button
            onClick={() => {
              setOpen(false)
              onLogout()
            }}
            className="flex w-full items-center gap-2 px-3 py-2 text-sm text-destructive transition-colors hover:bg-destructive/10"
          >
            <LogOut className="size-4" />
            退出登录
          </button>
        </div>
      )}
    </div>
  )
}

export default function AppLayout() {
  const { isAuthenticated, isLoading, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="text-muted-foreground text-sm">加载中...</div>
      </div>
    )
  }

  if (!isAuthenticated) {
    navigate("/admin/login", { replace: true })
    return null
  }

  const handleLogout = async () => {
    await logout()
    navigate("/admin/login", { replace: true })
  }

  const title =
    pageTitles[location.pathname] ||
    (location.pathname.startsWith("/admin/logs/") ? "日志详情" : "Kimi2API")

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className="flex w-60 flex-col bg-sidebar text-sidebar-foreground">
        {/* Brand */}
        <div className="flex items-center gap-3 px-5 py-5">
          <div className="size-8 rounded-lg bg-[#020617] p-1">
            <svg viewBox="0 0 64 64" className="size-full">
              <defs>
                <linearGradient id="sb-mark" x1="14" y1="12" x2="50" y2="52" gradientUnits="userSpaceOnUse">
                  <stop offset="0" stopColor="#60a5fa"/>
                  <stop offset="1" stopColor="#22c55e"/>
                </linearGradient>
              </defs>
              <path d="M20 17v30M23 32 39 18M23 32l17 15" fill="none" stroke="url(#sb-mark)" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M39 31h10m0 0-4-4m4 4-4 4" fill="none" stroke="#93c5fd" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"/>
              <circle cx="48" cy="44" r="3.5" fill="#22c55e"/>
            </svg>
          </div>
          <div>
            <h1 className="text-sm font-semibold tracking-tight">
              Kimi2API
            </h1>
            <p className="text-[11px] text-sidebar-foreground/50">
              管理控制台
            </p>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex flex-1 flex-col gap-0.5 px-3 pt-2">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-all ${
                  isActive
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-sidebar-foreground/60 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
                }`
              }
            >
              <item.icon className="size-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* Sidebar footer */}
        <div className="border-t border-sidebar-border p-3">
          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] text-sidebar-foreground/50 transition-colors hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
          >
            <LogOut className="size-4" />
            退出登录
          </button>
        </div>
      </aside>

      {/* Main area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-card px-6">
          <h2 className="text-sm font-medium text-foreground">{title}</h2>
          <UserMenu onLogout={handleLogout} />
        </header>

        {/* Content */}
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
