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
  const inFlightRef = useRef<{
    generation: number
    promise: Promise<void>
  } | null>(null)

  const startRefresh = useCallback((generation: number) => {
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

    inFlightRef.current = { generation, promise: request }
    void request.finally(() => {
      if (inFlightRef.current?.promise === request) {
        inFlightRef.current = null
      }
    })
    return request
  }, [fetcher])

  const runRefresh = useCallback((generation: number) => {
    const activeRequest = inFlightRef.current
    if (!activeRequest) {
      return startRefresh(generation)
    }
    if (activeRequest.generation === generation) {
      return activeRequest.promise
    }
    return activeRequest.promise.then(() => {
      if (generationRef.current !== generation) return
      return startRefresh(generation)
    })
  }, [startRefresh])

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
