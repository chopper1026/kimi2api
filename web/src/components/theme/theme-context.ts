import { createContext, useContext } from "react"

export type ThemeId = "tungsten-dark" | "daylight"

export interface ThemeOption {
  id: ThemeId
  label: string
  description: string
  appearance: "dark" | "light"
  enabled: boolean
}

export interface ThemeContextValue {
  theme: ThemeOption
  options: ThemeOption[]
  setTheme: (themeId: ThemeId) => void
}

export const THEME_STORAGE_KEY = "kimi2api.admin.theme"
export const DEFAULT_THEME: ThemeId = "tungsten-dark"

export const themeOptions: ThemeOption[] = [
  {
    id: "tungsten-dark",
    label: "Tungsten Night",
    description: "深石墨",
    appearance: "dark",
    enabled: true,
  },
  {
    id: "daylight",
    label: "Daylight",
    description: "即将支持",
    appearance: "light",
    enabled: false,
  },
]

export const enabledThemeIds = new Set(
  themeOptions.filter((option) => option.enabled).map((option) => option.id),
)

export const ThemeContext = createContext<ThemeContextValue | null>(null)

export function useDashboardTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error("useDashboardTheme must be used within ThemeProvider")
  }
  return context
}
