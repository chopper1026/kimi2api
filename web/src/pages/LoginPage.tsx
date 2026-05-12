import { useEffect, useRef, useState, type FormEvent } from "react"
import { useNavigate } from "react-router-dom"
import { CheckCircle2, Loader2 } from "lucide-react"
import { useAuth } from "@/hooks/use-auth"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { LogoMark } from "@/components/shared/LogoMark"
import { cn } from "@/lib/utils"

const LOGIN_BRIDGE_DURATION_MS = 760

export default function LoginPage() {
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loginState, setLoginState] =
    useState<"idle" | "submitting" | "bridge">("idle")
  const { login } = useAuth()
  const navigate = useNavigate()
  const navigationTimer = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (navigationTimer.current) {
        window.clearTimeout(navigationTimer.current)
      }
    }
  }, [])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError("")
    setLoginState("submitting")

    const err = await login(password)

    if (err) {
      setLoginState("idle")
      setError(err)
      return
    }

    setLoginState("bridge")
    navigationTimer.current = window.setTimeout(() => {
      navigate("/admin/dashboard", { replace: true })
    }, LOGIN_BRIDGE_DURATION_MS)
  }

  const isBusy = loginState !== "idle"
  const isBridge = loginState === "bridge"

  return (
    <div
      data-login-state={loginState}
      className={cn(
        "login-page-shell relative flex min-h-dvh items-center justify-center overflow-hidden bg-background px-4 py-8",
        isBridge && "login-bridge-active",
      )}
    >
      <div
        className={cn(
          "login-panel-layer w-full max-w-sm",
          isBridge && "login-panel-exit",
        )}
        aria-hidden={isBridge}
      >
        <div className="login-brand mb-8 flex flex-col items-center">
          <LogoMark className="size-11 p-1.5" />
          <h1 className="mt-4 text-lg font-semibold tracking-tight">
            Kimi2API
          </h1>
          <p className="mt-1 text-xs text-muted-foreground">
            管理控制台登录
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          aria-busy={isBusy}
          className={cn(
            "login-card rounded-xl border border-border/60 bg-card p-6 shadow-sm",
            isBridge && "login-card-bridge",
          )}
        >
          {error && (
            <div className="login-error mb-4 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
              {error}
            </div>
          )}
          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-xs text-muted-foreground">
                密码
              </label>
              <Input
                type="password"
                placeholder="请输入管理密码"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value)
                  if (error) setError("")
                }}
                disabled={isBusy}
                autoFocus
              />
            </div>
            <Button
              type="submit"
              disabled={isBusy || !password}
              className="w-full gap-2"
            >
              {loginState === "submitting" && (
                <Loader2 className="size-4 animate-spin" />
              )}
              {loginState === "submitting" ? "登录中..." : "登录"}
            </Button>
          </div>
        </form>
      </div>

      {isBridge && (
        <div className="login-bridge-page" role="status" aria-live="polite">
          <div className="login-bridge-mark">
            <LogoMark className="size-14 p-2" />
          </div>
          <div className="login-bridge-copy">
            <div className="flex items-center justify-center gap-2 text-sm font-medium text-foreground">
              <CheckCircle2 className="size-4 text-success" />
              正在进入控制台
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              正在建立安全会话
            </p>
          </div>
          <div className="login-bridge-progress" aria-hidden="true">
            <span />
          </div>
        </div>
      )}
    </div>
  )
}
