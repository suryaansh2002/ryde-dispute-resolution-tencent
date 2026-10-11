import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { initials } from '../components/Party'
import { RouteLegend, RouteLine } from '../components/RouteLine'
import { api } from '../lib/api'
import { duration } from '../lib/format'
import { savePersona } from '../lib/persona'
import { STATION_DEFS } from '../lib/pipeline'
import type { Station } from '../lib/pipeline'
import type { Category, Persona, Role, Stats } from '../types/api'

const SCENARIOS: { category: Category; title: string; who: string; text: string }[] = [
  {
    category: 'route_deviation',
    title: 'The long way round',
    who: 'Rider files',
    text: 'A rider says the driver took a longer route and charged more. The system measures the detour against the planned route and checks for traffic.',
  },
  {
    category: 'no_show_charge',
    title: 'Charged for a no-show',
    who: 'Rider files',
    text: 'A rider was charged $4.50 for not turning up. GPS shows whether the driver ever came within 100 m of the pickup.',
  },
  {
    category: 'property_damage',
    title: 'A mess in the back seat',
    who: 'Driver files',
    text: 'A driver claims a cleaning fee and attaches a photo. The fee comes from Ryde’s fixed tiers, never from the model.',
  },
  {
    category: 'safety_incident',
    title: 'Something felt unsafe',
    who: 'Rider files',
    text: 'Safety is never decided by an agent. Watch the claim leave the automated system at the first step.',
  },
]

// The illustrative line in the hero: a case that went all the way through.
const DEMO_STATIONS: Station[] = STATION_DEFS.map((d) => ({
  ...d,
  status: d.id === 'outcome' ? 'active' : 'done',
}))

function Metrics({ stats }: { stats: Stats | null }) {
  const decided = (stats?.decided_automatically ?? 0) + (stats?.decided_by_human ?? 0)
  const auto = decided ? Math.round(((stats?.decided_automatically ?? 0) / decided) * 100) : null
  const items = [
    { value: stats ? String(stats.cases) : '…', label: 'disputes filed in this demo' },
    { value: auto == null ? '—' : `${auto}%`, label: 'decided without a person, every gate passed' },
    { value: stats ? String(stats.awaiting_human) : '—', label: 'waiting for a human reviewer now' },
    { value: duration(stats?.median_seconds_to_decision), label: 'median time from claim to decision' },
  ]
  return (
    <section className="panel metrics" aria-label="Live numbers from this deployment">
      {items.map((m) => (
        <div key={m.label} className="metric">
          <span className="metric-value">{m.value}</span>
          <span className="small muted">{m.label}</span>
        </div>
      ))}
    </section>
  )
}

function PersonaPicker() {
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
    <section className="panel">
      <div className="panel-head">
        <div className="stack" style={{ gap: 2 }}>
          <h2>Or be someone</h2>
          <span className="small muted">Synthetic riders and drivers with real trip histories. No login.</span>
        </div>
        <div className="segmented" role="tablist">
          <button role="tab" aria-selected={role === 'rider'} className={role === 'rider' ? 'on' : ''} onClick={() => setRole('rider')}>
            Riders
          </button>
          <button role="tab" aria-selected={role === 'driver'} className={role === 'driver' ? 'on' : ''} onClick={() => setRole('driver')}>
            Drivers
          </button>
        </div>
      </div>
      {error && <p className="error-text panel-body">{error}</p>}
      {!personas && !error && (
        <div className="panel-body stack">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton" style={{ height: 34 }} />
          ))}
        </div>
      )}
      {personas?.length === 0 && (
        <div className="panel-body">
          <div className="empty">
            No synthetic users yet. Run <span className="mono">uv run python -m data_generation.pipeline.generate</span>
          </div>
        </div>
      )}
      <div className="grid-2" style={{ gap: 0 }}>
        {personas?.slice(0, showAll ? undefined : 8).map((p) => (
          <a
            key={p.id}
            className="list-row"
            style={{ borderTop: '1px solid var(--line)' }}
            href={`/${p.role}/${p.id}`}
            onClick={(e) => {
              e.preventDefault()
              choose(p)
            }}
          >
            <span className={`avatar ${p.role}`}>{initials(p.display_name)}</span>
            <div className="grow">
              <div style={{ fontWeight: 600 }}>{p.display_name}</div>
              <div className="tiny muted">
                {p.trips} trips · ★ {p.rating?.toFixed(2) ?? '—'}
                {p.dispute_count_30d >= 3 && ' · repeat filer'}
              </div>
            </div>
            {p.awaiting_my_response > 0 && <span className="badge tone-warn">{p.awaiting_my_response} to answer</span>}
          </a>
        ))}
      </div>
      {personas && personas.length > 8 && (
        <div className="panel-body" style={{ borderTop: '1px solid var(--line)' }}>
          <button className="btn-ghost btn-sm" onClick={() => setShowAll(!showAll)}>
            {showAll ? 'Show fewer' : `Show all ${personas.length}`}
          </button>
        </div>
      )}
    </section>
  )
}

export function Home() {
  const navigate = useNavigate()
  const [stats, setStats] = useState<Stats | null>(null)
  const [busy, setBusy] = useState<Category | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.stats().then(setStats, () => setStats(null))
  }, [])

  const run = async (category: Category) => {
    setBusy(category)
    setError(null)
    try {
      const s = await api.scenario(category)
      savePersona({ id: s.user_id, role: s.role, name: s.display_name })
      navigate(`/${s.role}/${s.user_id}/file/${s.trip_id}?demo=1&category=${category}`)
    } catch (e) {
      setError((e as Error).message)
      setBusy(null)
    }
  }

  return (
    <div className="stack" style={{ gap: 28 }}>
      <section className="hero">
        <div className="stack hero-text" style={{ gap: 16 }}>
          <span className="eyebrow">Ride-hailing dispute resolution</span>
          <h1>
            Every dispute gets a fair hearing: one advocate for the <span className="rider-word">rider</span>, one
            for the <span className="driver-word">driver</span>.
          </h1>
          <p className="lead">
            Five AI agents investigate route, no-show and damage disputes from the trip record. Two advocates argue
            each side from the same evidence, a Judge rules, and plain-code gates send anything uncertain, risky or
            safety-related to a person. Every finding cites evidence you can open.
          </p>
        </div>
        <div className="panel panel-pad stack" style={{ gap: 12 }}>
          <div className="row between">
            <span className="eyebrow">How a case travels</span>
            <span className="tiny faint">Open any case in the system trace to watch this line fill in live.</span>
          </div>
          <RouteLine stations={DEMO_STATIONS} />
          <RouteLegend />
        </div>
      </section>

      <section className="stack">
        <div className="row between">
          <div className="stack" style={{ gap: 2 }}>
            <h2>Run a demo case</h2>
            <span className="small muted">
              Picks a real synthetic trip that fits, signs you in as the person filing, and pre-fills the claim.
            </span>
          </div>
        </div>
        {error && <p className="error-text">{error}</p>}
        <div className="grid-4">
          {SCENARIOS.map((s) => (
            <button key={s.category} className="scenario" disabled={busy !== null} onClick={() => run(s.category)}>
              <span className="eyebrow">{s.who}</span>
              <span className="scenario-title">{s.title}</span>
              <span className="small muted">{s.text}</span>
              <span className="small" style={{ marginTop: 'auto', fontWeight: 600 }}>
                {busy === s.category ? (
                  <span className="row">
                    <span className="spinner" /> Finding a trip…
                  </span>
                ) : (
                  'Start →'
                )}
              </span>
            </button>
          ))}
        </div>
      </section>

      <Metrics stats={stats} />

      <div className="split">
        <PersonaPicker />
        <div className="stack">
          <Link to="/trace" className="panel entry">
            <span className="eyebrow">For judges and engineers</span>
            <h3>System trace</h3>
            <span className="small muted">
              Watch a case move through every agent and every gate, live. Click any citation to see the evidence
              behind it.
            </span>
            <span className="arrow">Open the trace →</span>
          </Link>
          <Link to="/l2" className="panel entry">
            <span className="eyebrow">For the support team</span>
            <h3>Human review</h3>
            <span className="small muted">
              Everything the gates escalated and every safety report, with the agents’ recommendation and the reason
              it needs a person.
            </span>
            <span className="arrow">Open the review queue →</span>
          </Link>
        </div>
      </div>
    </div>
  )
}
