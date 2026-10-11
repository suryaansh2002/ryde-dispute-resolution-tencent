import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { PartyPill, initials } from '../components/Party'
import { StateBadge } from '../components/StateBadge'
import { api } from '../lib/api'
import { CATEGORY_LABEL, IN_PROGRESS, money, when } from '../lib/format'
import { loadPersona } from '../lib/persona'
import type { CaseSummary, Role, Trip } from '../types/api'

const SCENARIO_LABEL: Record<string, string> = {
  route_deviation: 'route scenario',
  no_show_charge: 'no-show scenario',
  property_damage: 'damage scenario',
  safety_incident: 'safety scenario',
}

export function PartyPanel() {
  const { role, userId } = useParams() as { role: Role; userId: string }
  const persona = loadPersona()
  const name = persona?.id === userId ? persona.name : `This ${role}`
  const [trips, setTrips] = useState<Trip[] | null>(null)
  const [cases, setCases] = useState<CaseSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [allTrips, setAllTrips] = useState(false)

  const refresh = useCallback(() => {
    api.trips(userId).then(setTrips, (e: Error) => setError(e.message))
    api.userCases(userId).then(setCases, (e: Error) => setError(e.message))
  }, [userId])

  useEffect(refresh, [refresh])

  // Keep the list honest while any of this user's cases is still moving.
  const anyMoving = cases?.some((c) => IN_PROGRESS.includes(c.state)) ?? false
  useEffect(() => {
    if (!anyMoving) return
    const timer = setInterval(refresh, 5000)
    return () => clearInterval(timer)
  }, [anyMoving, refresh])

  const toAnswer = cases?.filter((c) => c.needs_my_response) ?? []
  const caseLink = (id: string) => `/${role}/${userId}/case/${id}`
  const shownTrips = trips?.slice(0, allTrips ? undefined : 8)

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="page-head" style={{ marginBottom: 0 }}>
        <div className="row" style={{ gap: 14 }}>
          <span className={`avatar ${role}`} style={{ width: 48, height: 48, fontSize: '1rem' }}>
            {initials(name)}
          </span>
          <div className="stack" style={{ gap: 4 }}>
            <h1>{name}</h1>
            <div className="row">
              <PartyPill role={role} />
              <span className="small muted">Report a problem with a trip, or answer one reported against you.</span>
            </div>
          </div>
        </div>
      </div>
      {error && <p className="error-text">{error}</p>}

      {toAnswer.length > 0 && (
        <section className="panel" style={{ borderColor: 'var(--warn)' }}>
          <div className="panel-head">
            <h2>Your side is needed</h2>
            <span className="badge tone-warn">{toAnswer.length} waiting</span>
          </div>
          {toAnswer.map((c) => (
            <Link key={c.id} to={caseLink(c.id)} className="list-row">
              <span className={`avatar ${role === 'rider' ? 'driver' : 'rider'}`}>{initials(c.other_party_name)}</span>
              <div className="grow">
                <div style={{ fontWeight: 600 }}>
                  {c.other_party_name} reported a {c.category ? CATEGORY_LABEL[c.category].toLowerCase() : 'problem'}
                </div>
                <div className="tiny muted">
                  <span className="mono">{c.id}</span> · {when(c.created_at)} · nothing is decided until you respond or
                  the window closes
                </div>
              </div>
              <span className="btn btn-primary btn-sm">Respond</span>
            </Link>
          ))}
        </section>
      )}

      <div className="grid-2" style={{ alignItems: 'start' }}>
        <section className="panel">
          <div className="panel-head">
            <h2>Your trips</h2>
            <span className="tiny muted">disputes allowed within 30 days</span>
          </div>
          {!trips && (
            <div className="panel-body stack">
              {[0, 1, 2].map((i) => (
                <div key={i} className="skeleton" style={{ height: 40 }} />
              ))}
            </div>
          )}
          {shownTrips?.map((t) => (
            <div key={t.id} className="list-row">
              <div className="grow">
                <div className="trip-route">
                  {when(t.completed_at)} · with {t.other_party_name}
                </div>
                <div className="tiny muted row" style={{ gap: 6 }}>
                  <span className="mono">{money(t.total_fare)}</span>
                  {(t.add_on_fees ?? []).map((f, i) => (
                    <span key={i}>
                      + {f.type.replaceAll('_', ' ')} <span className="mono">{money(f.amount)}</span>
                    </span>
                  ))}
                  {t.scenario_hint && SCENARIO_LABEL[t.scenario_hint] && (
                    <span className="badge" title="Synthetic-data label to help you find demo trips. The agents never see it.">
                      {SCENARIO_LABEL[t.scenario_hint]}
                    </span>
                  )}
                </div>
              </div>
              {t.case_id && t.case_state ? (
                <Link to={caseLink(t.case_id)}>
                  <StateBadge state={t.case_state} />
                </Link>
              ) : t.claimable ? (
                <Link to={`/${role}/${userId}/file/${t.id}`} className="btn btn-sm">
                  Report an issue
                </Link>
              ) : (
                <span className="tiny faint">past 30 days</span>
              )}
            </div>
          ))}
          {trips && trips.length > 8 && (
            <div className="panel-body" style={{ borderTop: '1px solid var(--line)' }}>
              <button className="btn-ghost btn-sm" onClick={() => setAllTrips(!allTrips)}>
                {allTrips ? 'Show fewer' : `Show all ${trips.length} trips`}
              </button>
            </div>
          )}
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>Your disputes</h2>
            <button className="btn-ghost btn-sm" onClick={refresh}>
              Refresh
            </button>
          </div>
          {!cases && (
            <div className="panel-body">
              <div className="skeleton" style={{ height: 40 }} />
            </div>
          )}
          {cases?.length === 0 && (
            <div className="panel-body">
              <div className="empty">No disputes yet. Pick a trip to report an issue.</div>
            </div>
          )}
          {cases?.map((c) => (
            <Link key={c.id} to={caseLink(c.id)} className="list-row">
              <div className="grow">
                <div style={{ fontWeight: 600 }}>{c.category ? CATEGORY_LABEL[c.category] : 'Dispute'}</div>
                <div className="tiny muted">
                  <span className="mono">{c.id}</span> ·{' '}
                  {c.my_side === 'complainer' ? `you reported ${c.other_party_name}` : `${c.other_party_name} reported you`} ·{' '}
                  {when(c.updated_at)}
                </div>
              </div>
              <StateBadge state={c.state} />
            </Link>
          ))}
        </section>
      </div>
    </div>
  )
}
