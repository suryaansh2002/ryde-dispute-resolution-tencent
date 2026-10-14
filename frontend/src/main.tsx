import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Link, Outlet, RouterProvider, createBrowserRouter, useLocation } from 'react-router-dom'
import './styles.css'
import { api } from './lib/api'
import { EvidenceProvider } from './components/evidence'
import { Mark } from './components/Icon'
import { Overview } from './routes/Overview'
import { PartyApp } from './routes/PartyApp'
import { Support } from './routes/Support'
import { Trace } from './routes/Trace'

const APPS: [string, string][] = [
  ['/', 'Overview'],
  ['/rider', 'Rider app'],
  ['/driver', 'Driver app'],
  ['/support', 'Support'],
  ['/trace', 'AI trace'],
]

/** The backend on a free tier sleeps; say so instead of showing empty pages. */
function useServer() {
  const [state, setState] = useState<'checking' | 'up' | 'down'>('checking')
  useEffect(() => {
    let on = true
    const check = () =>
      api.health().then(
        () => on && setState('up'),
        () => on && setState('down'),
      )
    check()
    const t = setInterval(check, 30000)
    return () => {
      on = false
      clearInterval(t)
    }
  }, [])
  return state
}

function Shell() {
  const { pathname } = useLocation()
  const server = useServer()
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [pathname])
  return (
    <EvidenceProvider>
      <header className="topbar">
        <div className="topbar-in">
          <Link className="brand" to="/"><Mark />RydeResolve</Link>
          <nav className="nav" aria-label="Apps">
            {APPS.map(([to, label]) => {
              const active = to === '/' ? pathname === '/' : pathname.startsWith(to) || (to === '/trace' && pathname.startsWith('/accuracy'))
              return (
                <Link key={to} to={to} aria-current={active ? 'page' : undefined}>{label}</Link>
              )
            })}
          </nav>
          <span className="spacer" />
          <span className="note">
            {server === 'down' ? <span style={{ color: 'var(--bad)' }}>Server unreachable · retrying</span> : 'Synthetic people, live pipeline'}
          </span>
        </div>
      </header>
      <main>
        <Outlet />
      </main>
    </EvidenceProvider>
  )
}

const router = createBrowserRouter([
  {
    element: <Shell />,
    children: [
      { path: '/', element: <Overview /> },
      { path: '/rider', element: <PartyApp key="rider" role="rider" /> },
      { path: '/driver', element: <PartyApp key="driver" role="driver" /> },
      { path: '/support', element: <Support /> },
      { path: '/support/:caseId', element: <Support /> },
      { path: '/trace', element: <Trace tab="cases" /> },
      { path: '/trace/:caseId', element: <Trace tab="cases" /> },
      { path: '/accuracy', element: <Trace tab="accuracy" /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
