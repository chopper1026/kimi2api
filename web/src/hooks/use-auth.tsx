import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from "react"
import { api, setCsrfToken } from "@/lib/api-client"

interface AuthContextValue {
  isAuthenticated: boolean
  isLoading: boolean
  login: (password: string) => Promise<string | null>
  logout: () => Promise<void>
  checkSession: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  const checkSession = useCallback(async () => {
    try {
      const session = await api.session()
      if (session.authenticated && session.csrf_token) {
        setCsrfToken(session.csrf_token)
        setIsAuthenticated(true)
      } else {
        setCsrfToken(null)
        setIsAuthenticated(false)
      }
    } catch {
      setCsrfToken(null)
      setIsAuthenticated(false)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    checkSession()
  }, [checkSession])

  const login = useCallback(async (password: string): Promise<string | null> => {
    try {
      const result = await api.login(password)
      if (result.success) {
        await checkSession()
        return null
      }
      return result.error || "登录失败"
    } catch (err: unknown) {
      if (err && typeof err === "object" && "data" in err) {
        return (err as { data: { error?: string } }).data?.error || "登录失败"
      }
      return "网络错误"
    }
  }, [checkSession])

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } finally {
      setCsrfToken(null)
      setIsAuthenticated(false)
    }
  }, [])

  return (
    <AuthContext.Provider
      value={{ isAuthenticated, isLoading, login, logout, checkSession }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
