import { useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { loadPersona } from '../lib/persona'
import { applyTheme, loadTheme } from '../lib/theme'
import type { ThemeChoice } from '../lib/theme'
import { initials } from './Party'
import { ServerStatus } from './ServerStatus'

export function Wordmark() {
  return (
    <Link to="/" className="wordmark" aria-label="RydeResolve home">
      <span className="wordmark-mark" aria-hidden>
        <svg width="16" height="16" viewBox="0 0 16 16">
          <path d="M2 8 H5 C7 8 7 4 9 4 M5 8 C7 8 7 12 9 12 M9 4 C11 4 11 8 14 8 M9 12 C11 12 11 8 14 8" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
        </svg>
      </span>
      RydeResolve
    </Link>
  )
}

const THEMES: { id: ThemeChoice; label: string }[] = [
  { id: 'system', label: 'Auto' },
  { id: 'light', label: 'Light' },
  { id: 'dark', label: 'Dark' },
]

export function Layout() {
  useLocation() // re-render on navigation so the persona indicator stays current
  const persona = loadPersona()
  const [theme, setTheme] = useState<ThemeChoice>(loadTheme())
  const choose = (t: ThemeChoice) => {
    setTheme(t)
    applyTheme(t)
  }

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <Wordmark />
          <nav className="nav" aria-label="Main">
            <NavLink to="/" end>
              Overview
            </NavLink>
            {persona && <NavLink to={`/${persona.role}/${persona.id}`}>My disputes</NavLink>}
            <NavLink to="/trace">System trace</NavLink>
            <NavLink to="/l2">Human review</NavLink>
            <NavLink to="/insights">Accuracy</NavLink>
          </nav>
          <span className="spacer" />
          {persona && (
            <Link to={`/${persona.role}/${persona.id}`} className="persona-chip" title="The persona you are viewing as">
              <span className={`avatar ${persona.role}`} style={{ width: 24, height: 24, fontSize: '0.66rem' }}>
                {initials(persona.name)}
              </span>
              <span className="small">
                {persona.name} <span className="faint">· {persona.role}</span>
              </span>
            </Link>
          )}
          <div className="segmented" role="radiogroup" aria-label="Colour theme">
            {THEMES.map((t) => (
              <button
                key={t.id}
                role="radio"
                aria-checked={theme === t.id}
                className={`btn-sm ${theme === t.id ? 'on' : ''}`}
                onClick={() => choose(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </header>
      <main>
        <ServerStatus />
        <Outlet />
      </main>
    </>
  )
}
