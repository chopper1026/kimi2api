import type { ApiError } from "@/types"

const API_BASE = "/admin/api"

let _csrfToken: string | null = null

export function setCsrfToken(token: string | null) {
  _csrfToken = token
}

export function getCsrfToken() {
  return _csrfToken
}

class ApiClientError extends Error {
  status: number
  data: ApiError

  constructor(status: number, data: ApiError) {
    super(data.error || "Request failed")
    this.status = status
    this.data = data
  }
}

export { ApiClientError }

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const headers: Record<string, string> = {
    ...(options?.headers as Record<string, string>),
  }

  if (_csrfToken && options?.method && options.method !== "GET") {
    headers["X-CSRF-Token"] = _csrfToken
  }

  if (options?.body && typeof options.body === "string") {
    headers["Content-Type"] = "application/json"
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: "same-origin",
  })

  const data = await res.json()

  if (!res.ok) {
    if (res.status === 401) {
      setCsrfToken(null)
    }
    throw new ApiClientError(res.status, data)
  }

  return data as T
}

export const api = {
  session: () => request<import("@/types").SessionInfo>("/session"),

  login: (password: string) =>
    request<{ success: boolean; error?: string }>("/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),

  logout: () =>
    request<{ success: boolean }>("/logout", { method: "POST" }),

  stats: () => request<import("@/types").DashboardStats>("/stats"),

  getToken: () => request<import("@/types").TokenInfo>("/token"),

  saveToken: (raw_token: string) =>
    request<import("@/types").TokenSaveResult>("/token", {
      method: "POST",
      body: JSON.stringify({ raw_token }),
    }),

  refreshToken: () =>
    request<import("@/types").TokenSaveResult>("/token/refresh", {
      method: "POST",
    }),

  validateToken: () =>
    request<import("@/types").TokenValidation>("/token/validate"),

  getKeys: () => request<import("@/types").KeysResponse>("/keys"),

  createKey: (name?: string) =>
    request<import("@/types").KeysResponse>("/keys", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  deleteKey: (key: string) =>
    request<import("@/types").KeysResponse>(`/keys/${key}`, {
      method: "DELETE",
    }),

  getLogs: (filters: Partial<import("@/types").LogFilters>) => {
    const params = new URLSearchParams()
    for (const [k, v] of Object.entries(filters)) {
      if (v) params.set(k, v)
    }
    const qs = params.toString()
    return request<import("@/types").LogsPage>(`/logs${qs ? `?${qs}` : ""}`)
  },

  getLogDetail: (requestId: string) =>
    request<import("@/types").LogDetailData>(`/logs/${requestId}`),
}
