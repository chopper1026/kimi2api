import { createContext, useContext } from "react"

export type ThemeId = "tungsten-dark" | "porcelain-moss"
export type ThemeMode = "system" | ThemeId

export interface ThemeOption {
  id: ThemeId
  label: string
  description: string
  appearance: "dark" | "light"
}

export interface ThemeModeOption {
  mode: ThemeMode
  label: string
  description: string
}

export interface ThemeContextValue {
  mode: ThemeMode
  theme: ThemeOption
  options: ThemeModeOption[]
  setMode: (mode: ThemeMode) => void
}

export const THEME_STORAGE_KEY = "kimi2api.admin.theme"
export const DEFAULT_THEME_MODE: ThemeMode = "system"

export const themeOptions: ThemeOption[] = [
  {
    id: "tungsten-dark",
    label: "Tungsten Night",
    description: "深石墨",
    appearance: "dark",
  },
  {
    id: "porcelain-moss",
    label: "Porcelain Moss",
    description: "瓷白灰绿",
    appearance: "light",
  },
]

export const themeModeOptions: ThemeModeOption[] = [
  {
    mode: "system",
    label: "跟随系统",
    description: "自动匹配",
  },
  {
    mode: "tungsten-dark",
    label: "Tungsten Night",
    description: "深石墨",
  },
  {
    mode: "porcelain-moss",
    label: "Porcelain Moss",
    description: "瓷白灰绿",
  },
]

export const enabledThemeModes = new Set<ThemeMode>(
  themeModeOptions.map((option) => option.mode),
)

export const ThemeContext = createContext<ThemeContextValue | null>(null)

export function useDashboardTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error("useDashboardTheme must be used within ThemeProvider")
  }
  return context
}
