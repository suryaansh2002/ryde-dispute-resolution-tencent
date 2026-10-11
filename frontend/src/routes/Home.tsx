import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { savePersona } from '../lib/persona'
import type { Persona, Role } from '../types/api'

export function Home() {
  const [role, setRole] = useState<Role>('rider')
  const [personas, setPersonas] = useState<Persona[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    setPersonas(null)
    setError(null)
    api.personas(role).then(setPersonas, (e: Error) => setError(e.message))
  }, [role])

  const choose = (p: Persona) => {
    savePersona({ id: p.id, role: p.role, name: p.display_name })
    navigate(`/${p.role}/${p.id}`)
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Who are you?</h1>
          <p>
            Pick a rider or driver to file and answer disputes, or open the L2 console as a human
            reviewer. There's no login: this is a demo with synthetic users.
          </p>
        </div>
        <div className="segmented" role="tablist">
          <button className={role === 'rider' ? 'on' : ''} onClick={() => setRole('rider')}>
            Riders
          </button>
          <button className={role === 'driver' ? 'on' : ''} onClick={() => setRole('driver')}>
            Drivers
          </button>
        </div>
      </div>

      <div className="grid-main">
        <section className="card">
          <div className="card-head">
            <h2>{role === 'rider' ? 'Riders' : 'Drivers'}</h2>
            <span className="small muted">sorted by open items, then dispute trips</span>
          </div>
          {error && <p className="error-text">{error}</p>}
          {!personas && !error && (
            <p className="muted">
              <span className="spinner" /> Loading…
            </p>
          )}
          {personas?.length === 0 && (
            <div className="empty">
              No synthetic users yet. Run the data generator:{' '}
              <span className="mono">uv run python -m data_generation.pipeline.generate</span>
            </div>
          )}
          <div className="list">
            {personas?.slice(0, showAll ? undefined : 12).map((p) => (
              <a
                key={p.id}
                className="list-item"
                href={`/${p.role}/${p.id}`}
                onClick={(e) => {
                  e.preventDefault()
                  choose(p)
                }}
              >
                <div className="grow">
                  <div className="title">{p.display_name}</div>
                  <div className="small muted">
                    {p.trips} trips · {p.scenario_trips} with a dispute scenario · rating{' '}
                    {p.rating?.toFixed(2) ?? '—'}
                    {p.dispute_count_30d >= 3 && ' · repeat filer'}
                  </div>
                </div>
                {p.awaiting_my_response > 0 && (
                  <span className="badge tone-warn">{p.awaiting_my_response} to answer</span>
                )}
              </a>
            ))}
          </div>
          {personas && personas.length > 12 && (
            <button className="small" style={{ marginTop: 8 }} onClick={() => setShowAll(!showAll)}>
              {showAll ? 'Show fewer' : `Show all ${personas.length}`}
            </button>
          )}
        </section>

        <aside className="stack">
          <section className="card">
            <h2>L2 human reviewer</h2>
            <p className="muted small">
              Cases the agents escalated, and every safety incident, land here for a person to
              ratify or override.
            </p>
            <Link to="/l2" className="button">
              Open the L2 console
            </Link>
          </section>
          <section className="card">
            <h2>System trace</h2>
            <p className="muted small">
              Watch any case live: triage, evidence collection, both advocates arguing from the
              same case file, the Judge's ruling, and every deterministic gate in between.
            </p>
            <Link to="/trace" className="button">
              Open the trace panel
            </Link>
          </section>
          <section className="card small muted">
            <strong>How a dispute flows.</strong> Claim → Triage agent → Prevention rules →
            Evidence collection agent → the other party responds → Rider and Driver advocates
            (in parallel) → Judge → escalation gate → compliance check → decision, or a human
            reviewer.
          </section>
        </aside>
      </div>
    </>
  )
}
