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
import { buttonVariants } from "@/components/ui/button-variants"
import { cn } from "@/lib/utils"
import { useState, useRef, useEffect, type SVGProps } from "react"

const GITHUB_REPO_URL = "https://github.com/chopper1026/kimi2api"

const navItems = [
  { to: "/admin/dashboard", label: "概览", icon: LayoutDashboard },
  { to: "/admin/token", label: "账号管理", icon: ShieldCheck },
  { to: "/admin/keys", label: "API Keys", icon: Key },
  { to: "/admin/logs", label: "请求日志", icon: ClipboardList },
]

const pageTitles: Record<string, string> = {
  "/admin/dashboard": "概览",
  "/admin/token": "账号管理",
  "/admin/keys": "API Keys",
  "/admin/logs": "请求日志",
}

function GitHubMark(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
      {...props}
    >
      <path d="M12 2C6.48 2 2 6.59 2 12.25c0 4.53 2.87 8.37 6.84 9.73.5.09.68-.22.68-.49 0-.24-.01-1.04-.01-1.89-2.51.47-3.16-.63-3.36-1.2-.11-.29-.6-1.2-1.03-1.45-.35-.2-.85-.69-.01-.7.79-.01 1.35.74 1.54 1.05.9 1.55 2.34 1.11 2.91.85.09-.67.35-1.11.64-1.37-2.22-.26-4.55-1.14-4.55-5.06 0-1.12.39-2.03 1.03-2.75-.1-.26-.45-1.3.1-2.71 0 0 .84-.28 2.75 1.05A9.28 9.28 0 0 1 12 7.01c.85 0 1.71.12 2.51.34 1.91-1.33 2.75-1.05 2.75-1.05.55 1.41.2 2.45.1 2.71.64.72 1.03 1.63 1.03 2.75 0 3.93-2.34 4.8-4.57 5.06.36.32.68.93.68 1.89 0 1.37-.01 2.47-.01 2.81 0 .27.18.59.69.49A10.17 10.17 0 0 0 22 12.25C22 6.59 17.52 2 12 2Z" />
    </svg>
  )
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
    <div
      data-admin-shell
      className="admin-shell-enter flex min-h-dvh flex-col bg-background md:h-screen md:flex-row"
    >
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
          <h2 className="min-w-0 truncate text-sm font-medium text-foreground">
            {title}
          </h2>
          <div className="flex shrink-0 items-center gap-1.5">
            <a
              href={GITHUB_REPO_URL}
              target="_blank"
              rel="noreferrer"
              aria-label="打开 GitHub 项目"
              title="GitHub 项目"
              className={cn(
                buttonVariants({ variant: "ghost", size: "icon" }),
                "size-10 text-muted-foreground hover:text-foreground",
              )}
            >
              <GitHubMark className="size-6" />
            </a>
            <UserMenu onLogout={handleLogout} />
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-auto p-4 pb-24 md:p-6">
          <div
            key={location.pathname}
            data-route-content
            className="admin-route-content min-h-full"
          >
            <Outlet />
          </div>
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
