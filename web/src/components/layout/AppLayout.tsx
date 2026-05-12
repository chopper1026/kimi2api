import { NavLink, Outlet, useNavigate, useLocation } from "react-router-dom"
import {
  LayoutDashboard,
  Key,
  ShieldCheck,
  ClipboardList,
  LogOut,
  ChevronDown,
  User,
  Palette,
  Check,
} from "lucide-react"
import { useAuth } from "@/hooks/use-auth"
import { useDashboardTheme } from "@/components/theme/theme-context"
import { LogoMark } from "@/components/shared/LogoMark"
import { cn } from "@/lib/utils"
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
  const { mode, theme, options, setMode } = useDashboardTheme()

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
        <div className="absolute right-0 top-full z-50 mt-1 min-w-[230px] overflow-hidden rounded-lg border border-border bg-popover py-1 shadow-xl">
          <div className="px-2 py-2">
            <div className="mb-1 flex items-center gap-1.5 px-2 text-[11px] font-medium text-muted-foreground">
              <Palette className="size-3.5" />
              主题
            </div>
            <div className="space-y-0.5">
              {options.map((option) => {
                const selected = option.mode === mode
                const description =
                  option.mode === "system"
                    ? `当前：${theme.appearance === "dark" ? "深色" : "浅色"}`
                    : option.description
                return (
                  <button
                    key={option.mode}
                    type="button"
                    onClick={() => setMode(option.mode)}
                    className={cn(
                      "flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left transition-colors",
                      "text-popover-foreground hover:bg-accent",
                      selected && "bg-accent text-accent-foreground",
                    )}
                  >
                    <span>
                      <span className="block text-xs font-medium">
                        {option.label}
                      </span>
                      <span className="block text-[10px] text-muted-foreground">
                        {description}
                      </span>
                    </span>
                    {selected && <Check className="size-3.5 text-primary" />}
                  </button>
                )
              })}
            </div>
          </div>
          <div className="border-t border-border" />
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
    <div className="flex min-h-dvh flex-col bg-background md:h-screen md:flex-row">
      {/* Sidebar */}
      <aside className="hidden w-60 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground md:flex">
        {/* Brand */}
        <div className="flex items-center gap-3 px-5 py-5">
          <LogoMark className="size-8" />
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
                    ? "bg-sidebar-accent text-sidebar-accent-foreground ring-1 ring-sidebar-ring/15"
                    : "text-sidebar-foreground/60 hover:bg-sidebar-accent/55 hover:text-sidebar-foreground"
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
            className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] text-sidebar-foreground/50 transition-colors hover:bg-sidebar-accent/55 hover:text-sidebar-foreground"
          >
            <LogOut className="size-4" />
            退出登录
          </button>
        </div>
      </aside>

      {/* Main area */}
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-background/80 px-4 md:px-6">
          <h2 className="text-sm font-medium text-foreground">{title}</h2>
          <UserMenu onLogout={handleLogout} />
        </header>

        {/* Content */}
        <main className="flex-1 overflow-auto p-4 pb-24 md:p-6">
          <Outlet />
        </main>
      </div>

      <nav
        aria-label="移动端导航"
        className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-background/95 px-2 pb-[calc(env(safe-area-inset-bottom)+0.5rem)] pt-2 shadow-[0_-10px_30px_rgba(0,0,0,0.08)] backdrop-blur md:hidden"
      >
        <div className="grid grid-cols-4 gap-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex min-h-12 flex-col items-center justify-center gap-1 rounded-lg px-1 text-[11px] font-medium transition-colors ${
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`
              }
            >
              <item.icon className="size-4" />
              <span className="truncate">{item.label}</span>
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  )
}
