import { useEffect, useState } from 'react'
import { api, evidenceContentUrl } from '../lib/api'
import { refKind, useEvidence } from '../lib/evidence'
import { money, when } from '../lib/format'
import type { EvidenceIndex, PolicyTag } from '../types/api'
import { RouteMap } from './RouteMap'

const KIND_TITLE: Record<string, string> = {
  chat: 'Chat message',
  photo: 'Photo evidence',
  traffic: 'Recorded traffic event',
  policy: 'Policy clause',
  history: 'Behaviour history',
  fare: 'Fare breakdown',
  gps: 'GPS record',
  route: 'Route',
  item: 'Evidence',
}

function Chat({ index, focus }: { index: EvidenceIndex; focus: string }) {
  const messages = Object.entries(index)
    .filter(([, item]) => item.kind === 'chat_message')
    .map(([ref, item]) => ({ ref, ...(item.data as { sender_role: 'rider' | 'driver'; text: string; timestamp: string }) }))
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp))
  return (
    <div className="chat">
      {messages.map((m) => (
        <div key={m.ref} className={`bubble ${m.sender_role}${m.ref === focus ? ' highlight' : ''}`}>
          <div className="bubble-meta">
            {m.ref} · {m.sender_role} · {when(m.timestamp)}
          </div>
          {m.text}
        </div>
      ))}
    </div>
  )
}

function Fare({ data }: { data: { base_fare: number; platform_fee: number; taxes: number; total_fare: number; add_on_fees: { type: string; amount: number }[] } }) {
  return (
    <dl className="kv">
      <dt>Base fare</dt>
      <dd className="mono">{money(data.base_fare)}</dd>
      <dt>Platform fee</dt>
      <dd className="mono">{money(data.platform_fee)}</dd>
      <dt>Taxes</dt>
      <dd className="mono">{money(data.taxes)}</dd>
      {data.add_on_fees.map((f, i) => (
        <span key={i} style={{ display: 'contents' }}>
          <dt>{f.type.replaceAll('_', ' ')}</dt>
          <dd className="mono">{money(f.amount)}</dd>
        </span>
      ))}
      <dt>
        <strong>Total charged</strong>
      </dt>
      <dd className="mono">
        <strong>{money(data.total_fare)}</strong>
      </dd>
    </dl>
  )
}

function RouteFacts({ index, refId }: { index: EvidenceIndex; refId: string }) {
  const pickupView = refId === 'PICKUP-PROXIMITY' || !index['ROUTE-COMPARISON']
  const c = pickupView ? null : index['ROUTE-COMPARISON']?.data
  const p = pickupView ? index['PICKUP-PROXIMITY']?.data : null
  return (
    <dl className="kv">
      {c && (
        <>
          <dt>Planned route</dt>
          <dd className="mono">{c.optimal_km.toFixed(2)} km</dd>
          <dt>Driven</dt>
          <dd className="mono">{c.actual_km.toFixed(2)} km</dd>
          <dt>Extra distance</dt>
          <dd className="mono">
            +{c.extra_km.toFixed(2)} km ({c.extra_pct.toFixed(1)}%)
          </dd>
          <dt>Policy tier</dt>
          <dd>{c.policy_tier.replaceAll('_', ' ').replace('pct', '%')}</dd>
          <dt>Refund if unjustified</dt>
          <dd className="mono">{money(c.refund_if_unjustified)}</dd>
        </>
      )}
      {p && (
        <>
          <dt>Closest approach to pickup</dt>
          <dd className="mono">{Math.round(p.closest_approach_m)} m</dd>
          <dt>Arrival radius</dt>
          <dd className="mono">{p.arrival_radius_m} m</dd>
          <dt>Reached pickup</dt>
          <dd>{p.reached_pickup ? 'Yes' : 'No'}</dd>
        </>
      )}
    </dl>
  )
}

function Profile({ data }: { data: { dispute_count_30d: number; upheld_denied_ratio: number | null; rating_trend: number | null; account_age_days: number; role: string } }) {
  return (
    <dl className="kv">
      <dt>Role</dt>
      <dd>{data.role}</dd>
      <dt>Disputes in 30 days</dt>
      <dd className="mono">
        {data.dispute_count_30d}
        {data.dispute_count_30d >= 3 && <span className="badge tone-warn" style={{ marginLeft: 8 }}>repeat filer</span>}
      </dd>
      <dt>Past claims upheld</dt>
      <dd className="mono">{data.upheld_denied_ratio == null ? 'no history' : `${Math.round(data.upheld_denied_ratio * 100)}%`}</dd>
      <dt>Rating trend</dt>
      <dd className="mono">{data.rating_trend == null ? '—' : data.rating_trend.toFixed(3)}</dd>
      <dt>Account age</dt>
      <dd className="mono">{data.account_age_days} days</dd>
    </dl>
  )
}

function Policy({ id }: { id: string }) {
  const [clauses, setClauses] = useState<PolicyTag[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    api.policy(id.slice(0, 6)).then(setClauses, (e: Error) => setError(e.message))
  }, [id])
  if (error) return <p className="error-text">{error}</p>
  if (!clauses) return <div className="skeleton" style={{ height: 120 }} />
  return (
    <div className="stack" style={{ gap: 10 }}>
      {clauses.map((c) => (
        <div key={c.chunk_id} className={`card${c.chunk_id === id ? ' system' : ''}`}>
          <div className="eyebrow">{c.chunk_id}</div>
          <p className="small" style={{ whiteSpace: 'pre-wrap', marginTop: 4 }}>
            {c.excerpt.split(' — ').slice(1).join(' — ') || c.excerpt}
          </p>
        </div>
      ))}
      <p className="tiny faint">
        Clauses marked "not Ryde-sourced" are the project’s own design choices; all other figures come
        from Ryde’s published policies.
      </p>
    </div>
  )
}

export function EvidenceDrawer({ refId, onClose }: { refId: string; onClose: () => void }) {
  const ctx = useEvidence()
  const [index, setIndex] = useState<EvidenceIndex | null>(null)
  const [error, setError] = useState<string | null>(null)
  const kind = refKind(refId)

  useEffect(() => {
    if (kind === 'policy' || !ctx) return
    ctx.load().then(setIndex, (e: Error) => setError(e.message))
  }, [ctx, kind])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const item = index?.[refId]
  let body = null
  if (kind === 'policy') body = <Policy id={refId} />
  else if (error) body = <p className="error-text">{error}</p>
  else if (!index) body = <div className="skeleton" style={{ height: 200 }} />
  else if (!item) body = <p className="muted">This item isn’t in the case file shown to you.</p>
  else if (item.kind === 'chat_message') body = <Chat index={index} focus={refId} />
  else if (item.kind === 'payment') body = <Fare data={item.data} />
  else if (item.kind === 'behavior_profile') body = <Profile data={item.data} />
  else if (item.kind === 'photo')
    body = (
      <div className="stack">
        <div className="mapbox" style={{ display: 'grid', placeItems: 'center', minHeight: 220 }}>
          <img
            src={evidenceContentUrl(item.data.evidence_id)}
            alt={`Photo evidence ${refId}`}
            style={{ maxWidth: '100%', maxHeight: 360, imageRendering: 'auto' }}
          />
        </div>
        <dl className="kv">
          <dt>Submitted</dt>
          <dd>{when(item.data.submitted_at)}</dd>
          <dt>Integrity hash</dt>
          <dd className="mono" style={{ wordBreak: 'break-all' }}>{item.data.hash}</dd>
        </dl>
        <p className="tiny faint">
          Verified to exist in object storage before the case file was assembled. Demo data uses placeholder
          images.
        </p>
      </div>
    )
  else if (item.kind === 'traffic_event')
    body = (
      <div className="stack">
        <RouteMap index={index} focus="traffic" />
        <dl className="kv">
          <dt>Type</dt>
          <dd>{String(item.data.type).replace('_', ' ')}</dd>
          <dt>Active</dt>
          <dd>
            {when(item.data.time_window_start)} – {when(item.data.time_window_end)}
          </dd>
          <dt>Description</dt>
          <dd>{item.data.description}</dd>
        </dl>
      </div>
    )
  else
    body = (
      <div className="stack">
        <RouteMap index={index} focus={kind === 'route' ? 'route' : 'gps'} />
        <RouteFacts index={index} refId={refId} />
      </div>
    )

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={`Evidence ${refId}`}>
        <div className="drawer-head">
          <div className="stack" style={{ gap: 4 }}>
            <span className="eyebrow">{KIND_TITLE[kind] ?? 'Evidence'}</span>
            <h2 className="mono" style={{ fontSize: '1.05rem' }}>
              {refId}
            </h2>
            <p className="tiny faint">
              {kind === 'policy'
                ? 'From the policy corpus the agents search.'
                : 'Exactly as it appears in the case file the agents cited from.'}
            </p>
          </div>
          <button className="btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            Close <kbd>Esc</kbd>
          </button>
        </div>
        <div className="drawer-body">{body}</div>
      </aside>
    </>
  )
}
