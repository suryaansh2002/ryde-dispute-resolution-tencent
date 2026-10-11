import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { StateBadge } from '../components/StateBadge'
import { api } from '../lib/api'
import { CATEGORY_LABEL, IN_PROGRESS, money, when } from '../lib/format'
import { loadPersona } from '../lib/persona'
import type { CaseSummary, Role, Trip } from '../types/api'

const SCENARIO_LABEL: Record<string, string> = {
  route_deviation: 'route deviation scenario',
  no_show_charge: 'no-show scenario',
  property_damage: 'property damage scenario',
  safety_incident: 'safety scenario',
}

export function PartyPanel() {
  const { role, userId } = useParams() as { role: Role; userId: string }
  const persona = loadPersona()
  const name = persona?.id === userId ? persona.name : `this ${role}`
  const [trips, setTrips] = useState<Trip[] | null>(null)
  const [cases, setCases] = useState<CaseSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

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

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{name}</h1>
          <p>
            {role === 'rider' ? 'Rider' : 'Driver'} panel: file a dispute on one of your trips, or
            answer one filed against you.
          </p>
        </div>
      </div>
      {error && <p className="error-text">{error}</p>}

      {toAnswer.length > 0 && (
        <section className="card" style={{ marginBottom: 16, borderColor: 'var(--warn)' }}>
          <h2>Waiting on your response</h2>
          <div className="list">
            {toAnswer.map((c) => (
              <Link key={c.id} to={caseLink(c.id)} className="list-item">
                <div className="grow">
                  <div className="title">
                    {c.other_party_name} filed a {c.category ? CATEGORY_LABEL[c.category].toLowerCase() : ''}{' '}
                    claim against you
                  </div>
                  <div className="small muted">
                    {c.id} · {when(c.created_at)}
                  </div>
                </div>
                <span className="button small">Respond</span>
              </Link>
            ))}
          </div>
        </section>
      )}

      <div className="grid-2">
        <section className="card">
          <div className="card-head">
            <h2>Your cases</h2>
            <button className="small" onClick={refresh}>
              Refresh
            </button>
          </div>
          {!cases && <p className="muted"><span className="spinner" /> Loading…</p>}
          {cases?.length === 0 && <div className="empty">No disputes yet.</div>}
          <div className="list">
            {cases?.map((c) => (
              <Link key={c.id} to={caseLink(c.id)} className="list-item">
                <div className="grow">
                  <div className="title">
                    {c.category ? CATEGORY_LABEL[c.category] : 'Dispute'}{' '}
                    <span className="muted small">
                      {c.my_side === 'complainer' ? `you filed, vs ${c.other_party_name}` : `filed by ${c.other_party_name}`}
                    </span>
                  </div>
                  <div className="small muted">
                    {c.id} · updated {when(c.updated_at)}
                  </div>
                </div>
                <StateBadge state={c.state} />
              </Link>
            ))}
          </div>
        </section>

        <section className="card">
          <div className="card-head">
            <h2>Your trips</h2>
            <span className="small muted">claims allowed within 30 days</span>
          </div>
          {!trips && <p className="muted"><span className="spinner" /> Loading…</p>}
          <div className="list">
            {trips?.map((t) => (
              <div key={t.id} className="list-item">
                <div className="grow">
                  <div className="title">
                    {when(t.completed_at)} with {t.other_party_name}
                  </div>
                  <div className="small muted row">
                    <span>fare {money(t.total_fare)}</span>
                    {t.scenario_hint && SCENARIO_LABEL[t.scenario_hint] && (
                      <span className="chip" title="Synthetic data label for demo navigation. Agents never see it.">
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
                  <Link to={`/${role}/${userId}/file/${t.id}`} className="button small">
                    File a claim
                  </Link>
                ) : (
                  <span className="small faint">outside claim window</span>
                )}
              </div>
            ))}
          </div>
        </section>
      </div>
    </>
  )
}
