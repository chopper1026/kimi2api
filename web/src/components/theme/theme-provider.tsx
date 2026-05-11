import { useEffect, useMemo, useState, type ReactNode } from "react"
import {
  DEFAULT_THEME_MODE,
  THEME_STORAGE_KEY,
  ThemeContext,
  enabledThemeModes,
  themeModeOptions,
  themeOptions,
  type ThemeContextValue,
  type ThemeId,
  type ThemeMode,
  type ThemeOption,
} from "@/components/theme/theme-context"

const SYSTEM_DARK_QUERY = "(prefers-color-scheme: dark)"

function getSystemPrefersDark() {
  return (
    typeof window !== "undefined" &&
    window.matchMedia(SYSTEM_DARK_QUERY).matches
  )
}

function getStoredMode(): ThemeMode {
  if (typeof window === "undefined") return DEFAULT_THEME_MODE
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY) as ThemeMode | null
    return stored && enabledThemeModes.has(stored) ? stored : DEFAULT_THEME_MODE
  } catch {
    return DEFAULT_THEME_MODE
  }
}

function persistMode(mode: ThemeMode) {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, mode)
  } catch {
    // Ignore storage failures and keep the in-memory choice for this session.
  }
}

function resolveThemeId(mode: ThemeMode, systemPrefersDark: boolean): ThemeId {
  if (mode === "system") {
    return systemPrefersDark ? "tungsten-dark" : "porcelain-moss"
  }
  return mode
}

function resolveTheme(mode: ThemeMode, systemPrefersDark: boolean) {
  const themeId = resolveThemeId(mode, systemPrefersDark)
  return (
    themeOptions.find((option) => option.id === themeId) ??
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
  const [mode, setThemeMode] = useState<ThemeMode>(getStoredMode)
  const [systemPrefersDark, setSystemPrefersDark] = useState(getSystemPrefersDark)
  const theme = resolveTheme(mode, systemPrefersDark)

  useEffect(() => {
    const mediaQuery = window.matchMedia(SYSTEM_DARK_QUERY)
    const handleChange = () => setSystemPrefersDark(mediaQuery.matches)

    handleChange()
    mediaQuery.addEventListener("change", handleChange)
    return () => mediaQuery.removeEventListener("change", handleChange)
  }, [])

  useEffect(() => {
    applyTheme(theme)
    persistMode(mode)
  }, [mode, theme])

  const value = useMemo<ThemeContextValue>(
    () => ({
      mode,
      theme,
      options: themeModeOptions,
      setMode(nextMode) {
        if (!enabledThemeModes.has(nextMode)) return
        setThemeMode(nextMode)
      },
    }),
    [mode, theme],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
