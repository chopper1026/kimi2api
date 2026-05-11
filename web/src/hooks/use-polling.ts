import { useEffect, useCallback, useRef, useState } from "react"

export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
  enabled = true,
) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const generationRef = useRef(0)
  const inFlightRef = useRef<Promise<void> | null>(null)

  const runRefresh = useCallback((generation: number) => {
    if (inFlightRef.current) {
      return inFlightRef.current
    }

    const request = (async () => {
      try {
        if (generationRef.current === generation) {
          setError(null)
        }
        const result = await fetcher()
        if (generationRef.current === generation) {
          setData(result)
        }
      } catch (err: unknown) {
        if (generationRef.current === generation) {
          const msg = err instanceof Error ? err.message : "请求失败"
          setError(msg)
        }
      } finally {
        if (generationRef.current === generation) {
          setLoading(false)
        }
      }
    })()

    inFlightRef.current = request
    void request.finally(() => {
      if (inFlightRef.current === request) {
        inFlightRef.current = null
      }
    })
    return request
  }, [fetcher])

  const refresh = useCallback(() => {
    return runRefresh(generationRef.current)
  }, [runRefresh])

  useEffect(() => {
    if (!enabled) return

    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const generation = generationRef.current + 1
    generationRef.current = generation

    const poll = async () => {
      await runRefresh(generation)
      if (!cancelled) {
        timer = setTimeout(() => {
          void poll()
        }, intervalMs)
      }
    }

    void poll()

    return () => {
      cancelled = true
      generationRef.current += 1
      if (timer) {
        clearTimeout(timer)
      }
    }
  }, [intervalMs, enabled, runRefresh])

  return { data, loading, error, refresh }
}
