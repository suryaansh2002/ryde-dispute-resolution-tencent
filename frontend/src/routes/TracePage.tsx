import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { PartyName } from '../components/Party'
import { RouteLegend, RouteLine } from '../components/RouteLine'
import { StateBadge } from '../components/StateBadge'
import { TraceTimeline } from '../components/TraceTimeline'
import { api, streamUrl } from '../lib/api'
import { EvidenceProvider } from '../lib/evidence'
import { CATEGORY_LABEL, IN_PROGRESS, ago, duration } from '../lib/format'
import { STAGE_CAPTION, currentStation, deriveStations } from '../lib/pipeline'
import type { StationId } from '../lib/pipeline'
import { useEventStream } from '../lib/useEventStream'
import type { Argument, CaseView, DecisionObject, RecentCase, Role, TraceEvent } from '../types/api'

function summarize(events: TraceEvent[]) {
  const first = events[0]?.t
  const end = events.find(
    (e) => e.kind === 'state_transition' && /-> (decided|escalated|safety_bypassed|declined)/.test(e.detail ?? ''),
  )?.t
  let cites = 0
  for (const e of events) {
    if (e.kind !== 'agent_output' || !e.output) continue
    if (e.agent === 'rider_advocate' || e.agent === 'driver_advocate') {
      const a = e.output as unknown as Argument
      cites += a.cites.length + a.policy_cites.length
    }
    if (e.agent === 'judge') {
      const d = e.output as unknown as DecisionObject
      cites += d.reasoning.reduce((n, f) => n + f.cites.length, 0)
    }
  }
  const agents = new Set(events.filter((e) => e.kind === 'agent_output').map((e) => e.agent)).size
  return {
    seconds: first && end ? (new Date(end).getTime() - new Date(first).getTime()) / 1000 : null,
    cites,
    agents,
  }
}

function CaseTrace({ caseId }: { caseId: string }) {
  const { events, status } = useEventStream<TraceEvent>(streamUrl.case(caseId))
  const [view, setView] = useState<CaseView | null>(null)
  const [selected, setSelected] = useState<StationId | null>(null)
  const lastId = events[events.length - 1]?.id

  // A trace event can land a moment before the case row is updated: read twice.
  useEffect(() => {
    const read = () => api.caseView(caseId).then(setView, () => setView(null))
    read()
    const t = setTimeout(read, 1500)
    return () => clearTimeout(t)
  }, [caseId, lastId])

  const stations = useMemo(() => deriveStations(events), [events])
  const current = currentStation(stations)
  const captionId = selected ?? current?.id ?? null
  const caption = captionId ? STAGE_CAPTION[captionId] : null
  const sum = useMemo(() => summarize(events), [events])
  const working = view ? IN_PROGRESS.includes(view.state) : false
  const complaineeRole: Role | null = view ? (view.complainer_role === 'rider' ? 'driver' : 'rider') : null

  return (
    <EvidenceProvider caseId={caseId} view="operator">
      <div className="stack" style={{ gap: 16 }}>
        <section className="panel">
          <div className="panel-head" style={{ alignItems: 'flex-start' }}>
            <div className="stack" style={{ gap: 4 }}>
              <span className="eyebrow">
                Case <span className="mono">{caseId}</span>
              </span>
              <h2 style={{ fontSize: '1.35rem' }}>{view?.category ? CATEGORY_LABEL[view.category] : 'Case'}</h2>
              {view && complaineeRole && (
                <div className="small row" style={{ gap: 6 }}>
                  <PartyName role={view.complainer_role} name={view.complainer_name} />
                  <span className="faint">reported</span>
                  <PartyName role={complaineeRole} name={view.complainee_name} />
                </div>
              )}
            </div>
            <div className="row">
              {view && <StateBadge state={view.state} />}
              <span className={`badge ${status === 'open' ? 'tone-good' : ''}`} title="Server-sent events stream">
                <span className={`dot${status === 'open' ? '' : ' pulse'}`} />
                {status === 'open' ? 'Live' : status}
              </span>
            </div>
          </div>
          <div className="metrics" style={{ borderBottom: '1px solid var(--line)' }}>
            <div className="metric">
              <span className="metric-value" style={{ fontSize: '1.2rem' }}>
                {sum.seconds == null ? (working ? '…' : '—') : duration(sum.seconds)}
              </span>
              <span className="tiny muted">claim to outcome</span>
            </div>
            <div className="metric">
              <span className="metric-value" style={{ fontSize: '1.2rem' }}>
                {sum.agents}
              </span>
              <span className="tiny muted">agents have run</span>
            </div>
            <div className="metric">
              <span className="metric-value" style={{ fontSize: '1.2rem' }}>
                {sum.cites}
              </span>
              <span className="tiny muted">evidence citations</span>
            </div>
            <div className="metric">
              <span className="metric-value" style={{ fontSize: '1.2rem' }}>
                {events.length}
              </span>
              <span className="tiny muted">trace events</span>
            </div>
          </div>
          <div className="panel-body stack" style={{ gap: 12 }}>
            <RouteLine stations={stations} onSelect={(id) => setSelected(id === selected ? null : id)} selected={selected} />
            <RouteLegend />
            {caption && (
              <div className="caption">
                {working && !selected ? <span className="spinner" style={{ marginTop: 3 }} /> : null}
                <div>
                  <strong>{caption.title}.</strong> <span className="muted">{caption.text}</span>
                </div>
              </div>
            )}
          </div>
        </section>

        {view?.claim_text && complaineeRole && (
          <section className="panel hearing">
            <div className="panel-head">
              <h3>What each side said</h3>
              <span className="tiny faint">Seen by the advocates. Never by the Judge.</span>
            </div>
            <div className="panel-body versus">
              <div className="stack" style={{ gap: 6 }}>
                <PartyName role={view.complainer_role} name={`${view.complainer_name}, the claim`} />
                <p className="quote" style={{ ['--party' as string]: `var(--${view.complainer_role})` }}>
                  {view.claim_text}
                </p>
              </div>
              <div className="stack" style={{ gap: 6 }}>
                <PartyName role={complaineeRole} name={`${view.complainee_name}, the response`} />
                {view.response ? (
                  <p className="quote" style={{ ['--party' as string]: `var(--${complaineeRole})` }}>
                    {view.response.text}
                  </p>
                ) : (
                  <p className="small faint">{view.state === 'awaiting_response' ? 'Waiting for a response…' : 'No response given.'}</p>
                )}
              </div>
            </div>
          </section>
        )}

        <section className="panel">
          <div className="panel-head">
            <h3>Trace</h3>
            <span className="tiny faint">Every agent output and every rule, in order. Citations open the evidence.</span>
          </div>
          <div className="panel-body">
            <TraceTimeline events={events} working={working} category={view?.category ?? null} />
          </div>
        </section>
      </div>
    </EvidenceProvider>
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
    <div className="stack" style={{ gap: 20 }}>
      <div className="page-head" style={{ marginBottom: 0 }}>
        <div className="stack" style={{ gap: 6 }}>
          <h1>System trace</h1>
          <p className="lead">
            Every agent and every deterministic gate, as it happens. The advocates argue from the same case file; the
            Judge sees their arguments and the evidence, never the complaint.
          </p>
        </div>
      </div>
      {error && <p className="error-text">{error}</p>}
      <div className="split-left">
        <section className="panel sticky">
          <div className="panel-head">
            <h3>Recent cases</h3>
            <span className="tiny faint">{cases?.length ?? ''}</span>
          </div>
          {cases?.length === 0 && (
            <div className="panel-body">
              <div className="empty">
                No cases yet. <Link to="/">Run a demo case</Link>.
              </div>
            </div>
          )}
          <div style={{ maxHeight: '70vh', overflowY: 'auto' }}>
            {cases?.map((c) => (
              <Link
                key={c.id}
                to={`/trace/${c.id}`}
                className="list-row"
                style={{ padding: '10px 16px', ...(c.id === caseId ? { background: 'var(--surface-3)', boxShadow: 'inset 3px 0 0 var(--ink)' } : {}) }}
              >
                <div className="grow">
                  <div className="small" style={{ fontWeight: 600 }}>
                    {c.category ? CATEGORY_LABEL[c.category] : '—'}
                  </div>
                  <div className="tiny faint">
                    <span className="mono">{c.id}</span> · {ago(c.updated_at)}
                  </div>
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
    </div>
  )
}
