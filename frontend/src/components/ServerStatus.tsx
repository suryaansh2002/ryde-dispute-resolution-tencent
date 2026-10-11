import { useEffect, useState } from 'react'
import { API_URL, api } from '../lib/api'

type Status = 'checking' | 'slow' | 'up' | 'down'

/** The backend runs on a free tier that sleeps when idle; the first request can take
 * about a minute. Say so instead of looking broken. */
export function ServerStatus() {
  const [status, setStatus] = useState<Status>('checking')

  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()
    const slowTimer = setTimeout(() => !cancelled && setStatus('slow'), 2500)
    const giveUp = setTimeout(() => controller.abort(), 90_000)
    api
      .health(controller.signal)
      .then(() => !cancelled && setStatus('up'))
      .catch(() => !cancelled && setStatus('down'))
      .finally(() => {
        clearTimeout(slowTimer)
        clearTimeout(giveUp)
      })
    return () => {
      cancelled = true
      controller.abort()
      clearTimeout(slowTimer)
      clearTimeout(giveUp)
    }
  }, [])

  if (status === 'slow')
    return (
      <div className="banner tone-live">
        <span className="spinner" /> Waking the backend. It sleeps when idle and can take up to
        a minute to start.
      </div>
    )
  if (status === 'down')
    return (
      <div className="banner tone-bad">
        Can't reach the backend at <span className="mono">{API_URL}</span>. Check that it's
        running and that <span className="mono">VITE_API_URL</span> points at it.
      </div>
    )
  return null
}
