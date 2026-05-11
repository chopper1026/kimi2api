import { useEffect, useMemo, useState, type ReactNode } from "react"
import {
  DEFAULT_THEME,
  THEME_STORAGE_KEY,
  ThemeContext,
  enabledThemeIds,
  themeOptions,
  type ThemeContextValue,
  type ThemeId,
  type ThemeOption,
} from "@/components/theme/theme-context"

function getStoredTheme(): ThemeId {
  if (typeof window === "undefined") return DEFAULT_THEME
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY) as ThemeId | null
  return stored && enabledThemeIds.has(stored) ? stored : DEFAULT_THEME
}

function resolveTheme(themeId: ThemeId) {
  return (
    themeOptions.find((option) => option.id === themeId && option.enabled) ??
    themeOptions[0]
  )
}

function applyTheme(theme: ThemeOption) {
  const root = document.documentElement
  root.dataset.theme = theme.id
  root.classList.toggle("dark", theme.appearance === "dark")
  root.style.colorScheme = theme.appearance
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [themeId, setThemeId] = useState<ThemeId>(getStoredTheme)
  const theme = resolveTheme(themeId)

  useEffect(() => {
    applyTheme(theme)
    window.localStorage.setItem(THEME_STORAGE_KEY, theme.id)
  }, [theme])

  const value = useMemo<ThemeContextValue>(
    () => ({
      theme,
      options: themeOptions,
      setTheme(nextThemeId) {
        if (!enabledThemeIds.has(nextThemeId)) return
        setThemeId(nextThemeId)
      },
    }),
    [theme],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
