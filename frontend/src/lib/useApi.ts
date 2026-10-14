import { useCallback, useEffect, useState } from 'react'

// One cache for every GET the app makes, keyed by a string the caller picks. Evidence,
// policy text and finished decisions don't change, so citation popovers, the drawer and
// the pages all share one fetch. `reload()` (or `invalidate`) refetches.
const cache = new Map<string, Promise<unknown>>()

export function invalidate(prefix: string) {
  for (const k of [...cache.keys()]) if (k.startsWith(prefix)) cache.delete(k)
}

export function cached<T>(key: string, fn: () => Promise<T>): Promise<T> {
  let p = cache.get(key) as Promise<T> | undefined
  if (!p) {
    p = fn()
    cache.set(key, p)
    p.catch(() => cache.delete(key))
  }
  return p
}

export interface ApiState<T> {
  data: T | undefined
  error: Error | undefined
  loading: boolean
  reload: () => void
}

/** `key` null means "not yet": nothing is fetched until the inputs exist. `fresh` skips
 * the cache for data that changes under us (a case's current state). */
export function useApi<T>(key: string | null, fn: () => Promise<T>, fresh = false): ApiState<T> {
  const [state, setState] = useState<{ key: string | null; data?: T; error?: Error }>({ key: null })
  const [tick, setTick] = useState(0)

  useEffect(() => {
    if (key == null) return
    let live = true
    ;(fresh ? fn() : cached(key, fn)).then(
      (data) => live && setState({ key, data }),
      (error: Error) => live && setState({ key, error }),
    )
    return () => {
      live = false
    }
    // fn is recreated every render; the key names what it fetches
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, tick])

  const reload = useCallback(() => {
    if (key != null) cache.delete(key)
    setTick((t) => t + 1)
  }, [key])

  const current = state.key === key
  return {
    data: current ? state.data : undefined,
    error: current ? state.error : undefined,
    loading: key != null && (!current || (state.data === undefined && state.error === undefined)),
    reload,
  }
}
