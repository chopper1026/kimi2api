import { useState, type FormEvent } from "react"
import { useNavigate } from "react-router-dom"
import { useAuth } from "@/hooks/use-auth"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { LogoMark } from "@/components/shared/LogoMark"

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
