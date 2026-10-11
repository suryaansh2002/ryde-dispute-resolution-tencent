import { useEffect, useRef, useState } from 'react'

export type StreamStatus = 'connecting' | 'open' | 'reconnecting'

/**
 * Subscribes to an SSE endpoint and accumulates its events, de-duplicated by id.
 * The backend replays history first, then streams live. EventSource reconnects on its
 * own and sends Last-Event-ID, so a dropped connection resumes without duplicates.
 */
export function useEventStream<T extends { id: number }>(url: string | null) {
  const [events, setEvents] = useState<T[]>([])
  const [status, setStatus] = useState<StreamStatus>('connecting')
  const seen = useRef(new Set<number>())

  useEffect(() => {
    setEvents([])
    seen.current = new Set()
    if (!url) return
    setStatus('connecting')
    const source = new EventSource(url)
    source.onopen = () => setStatus('open')
    source.onerror = () => setStatus('reconnecting')
    source.onmessage = (message) => {
      let event: T
      try {
        event = JSON.parse(message.data) as T
      } catch {
        return
      }
      if (seen.current.has(event.id)) return
      seen.current.add(event.id)
      setEvents((prev) => [...prev, event])
    }
    return () => source.close()
  }, [url])

  return { events, status }
}
