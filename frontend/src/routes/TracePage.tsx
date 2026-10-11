import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { StateBadge } from '../components/StateBadge'
import { TraceTimeline } from '../components/TraceTimeline'
import { api, streamUrl } from '../lib/api'
import { CATEGORY_LABEL, IN_PROGRESS, when } from '../lib/format'
import { useEventStream } from '../lib/useEventStream'
import type { CaseView, RecentCase, TraceEvent } from '../types/api'

function CaseTrace({ caseId }: { caseId: string }) {
  const { events, status } = useEventStream<TraceEvent>(streamUrl.case(caseId))
  const [view, setView] = useState<CaseView | null>(null)
  const lastId = events[events.length - 1]?.id

  useEffect(() => {
    api.caseView(caseId).then(setView, () => setView(null))
  }, [caseId, lastId])

  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>
            {view?.category ? CATEGORY_LABEL[view.category] : 'Case'}{' '}
            <span className="mono muted" style={{ fontSize: '0.85rem' }}>
              {caseId}
            </span>
          </h2>
          {view && (
            <div className="small muted">
              {view.complainer_name} ({view.complainer_role}) vs {view.complainee_name}
            </div>
          )}
        </div>
        <div className="row">
          {view && <StateBadge state={view.state} />}
          <span className={`badge ${status === 'open' ? 'tone-good' : 'tone-neutral'}`}>
            <span className={`dot${status === 'open' ? '' : ' pulse'}`} />
            {status === 'open' ? 'live' : status}
          </span>
        </div>
      </div>
      {view?.claim_text && (
        <p className="small muted" style={{ marginTop: 0 }}>
          <strong>Claim:</strong> {view.claim_text}
          {view.response && (
            <>
              <br />
              <strong>Response:</strong> {view.response.text}
            </>
          )}
        </p>
      )}
      <TraceTimeline events={events} working={view ? IN_PROGRESS.includes(view.state) : false} />
    </section>
  )
}

export function TracePage() {
  const { caseId } = useParams()
  const [cases, setCases] = useState<RecentCase[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const load = () => api.recentCases(40).then(setCases, (e: Error) => setError(e.message))
    load()
    const timer = setInterval(load, 8000)
    return () => clearInterval(timer)
  }, [])

  return (
    <>
      <div className="page-head">
        <div>
          <h1>System trace</h1>
          <p>
            Every agent output and every deterministic gate, as it happens. Advocates argue from the
            same case file; the Judge sees their arguments, never the raw complaint.
          </p>
        </div>
      </div>
      {error && <p className="error-text">{error}</p>}
      <div className="grid-main" style={{ gridTemplateColumns: 'minmax(0, 300px) minmax(0, 1fr)' }}>
        <section className="card" style={{ padding: 8 }}>
          <h3 style={{ padding: '6px 8px' }}>Recent cases</h3>
          {cases?.length === 0 && <div className="empty">No cases yet. File one from a persona.</div>}
          <div className="list">
            {cases?.map((c) => (
              <Link
                key={c.id}
                to={`/trace/${c.id}`}
                className={`list-item${c.id === caseId ? ' selected' : ''}`}
                style={{ padding: '8px' }}
              >
                <div className="grow">
                  <div className="title small">
                    {c.id} · {c.category ? CATEGORY_LABEL[c.category] : '—'}
                  </div>
                  <div className="small faint">{when(c.updated_at)}</div>
                </div>
                <StateBadge state={c.state} />
              </Link>
            ))}
          </div>
        </section>
        {caseId ? (
          <CaseTrace key={caseId} caseId={caseId} />
        ) : (
          <div className="empty">Pick a case to watch its trace.</div>
        )}
      </div>
    </>
  )
}
