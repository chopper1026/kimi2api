import { useState, type FormEvent } from "react"
import { useNavigate } from "react-router-dom"
import { useAuth } from "@/hooks/use-auth"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export default function LoginPage() {
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)

    const err = await login(password)
    setLoading(false)

    if (err) {
      setError(err)
      return
    }

    navigate("/admin/dashboard", { replace: true })
  }

  return (
    <div className="flex h-screen items-center justify-center bg-background">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center">
          <div className="size-11 rounded-xl bg-[#020617] p-1.5 shadow-sm">
            <svg viewBox="0 0 64 64" className="size-full">
              <defs>
                <linearGradient id="lg-mark" x1="14" y1="12" x2="50" y2="52" gradientUnits="userSpaceOnUse">
                  <stop offset="0" stopColor="#60a5fa"/>
                  <stop offset="1" stopColor="#22c55e"/>
                </linearGradient>
              </defs>
              <path d="M20 17v30M23 32 39 18M23 32l17 15" fill="none" stroke="url(#lg-mark)" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M39 31h10m0 0-4-4m4 4-4 4" fill="none" stroke="#93c5fd" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"/>
              <circle cx="48" cy="44" r="3.5" fill="#22c55e"/>
            </svg>
          </div>
          <h1 className="mt-4 text-lg font-semibold tracking-tight">
            Kimi2API
          </h1>
          <p className="mt-1 text-xs text-muted-foreground">
            管理控制台登录
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="rounded-xl border border-border/60 bg-card p-6 shadow-sm"
        >
          {error && (
            <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
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
                onChange={(e) => setPassword(e.target.value)}
                autoFocus
              />
            </div>
            <Button
              type="submit"
              disabled={loading || !password}
              className="w-full"
            >
              {loading ? "登录中..." : "登录"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
