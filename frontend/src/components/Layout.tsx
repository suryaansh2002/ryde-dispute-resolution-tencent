import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { loadPersona } from '../lib/persona'
import { ServerStatus } from './ServerStatus'

export function Layout() {
  useLocation() // re-render on navigation so the persona indicator stays current
  const persona = loadPersona()
  const panel = persona ? `/${persona.role}/${persona.id}` : null

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <NavLink to="/" className="brand">
            <img src="/favicon.svg" alt="" />
            RydeResolve
          </NavLink>
          <nav className="nav">
            <NavLink to="/" end>
              Personas
            </NavLink>
            {panel && <NavLink to={panel}>My panel</NavLink>}
            <NavLink to="/trace">System trace</NavLink>
            <NavLink to="/l2">L2 console</NavLink>
          </nav>
          <span className="spacer" />
          {persona && (
            <span className="whoami">
              Viewing as <strong>{persona.name}</strong> ({persona.role})
            </span>
          )}
        </div>
      </header>
      <main>
        <ServerStatus />
        <Outlet />
      </main>
    </>
  )
}
