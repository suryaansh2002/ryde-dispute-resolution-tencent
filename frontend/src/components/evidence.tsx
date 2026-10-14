import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import type { EvidenceIndex, EvidenceItem } from '../types/api'
import { evidenceContentUrl } from '../lib/api'
import { clock, money } from '../lib/format'
import { useEvidence } from '../lib/live'
import { Icon, type IconName } from './Icon'
import { POLICY_INFO, PolicyView } from './PolicyView'
import { TripMap, geoFromEvidence } from './TripMap'

/* Citation chip → hover preview → drawer with the full item. The signature move: any
   claim an agent makes opens the exact evidence it rests on. */

const EvidenceCtx = createContext<{ open: (caseId: string, refId: string) => void }>({ open: () => {} })

export function EvidenceProvider({ children }: { children: ReactNode }) {
  const [drawer, setDrawer] = useState<{ caseId: string; refId: string } | null>(null)
  return (
    <EvidenceCtx.Provider value={{ open: (caseId, refId) => setDrawer({ caseId, refId }) }}>
      {children}
      {drawer && <Drawer caseId={drawer.caseId} refId={drawer.refId} onClose={() => setDrawer(null)} />}
    </EvidenceCtx.Provider>
  )
}

export function refKind(ref: string): [string, IconName] {
  if (ref.startsWith('MSG-')) return ['Message', 'msg']
  if (ref.startsWith('EV-')) return ['Photo', 'camera']
  if (ref.startsWith('TRAFFIC-')) return ['Traffic', 'alert']
  if (ref.startsWith('POL-')) return ['Policy', 'file']
  if (ref.startsWith('PROFILE-')) return ['History', 'user']
  if (ref === 'PAYMENT') return ['Fare', 'receipt']
  if (ref === 'PICKUP-PROXIMITY' || ref === 'GPS-TRACE') return ['GPS', 'pin']
  return ['Route', 'route']
}

export const photoUrl = (item: EvidenceItem) => evidenceContentUrl(item.data.evidence_id)

function Preview({ caseId, refId, ev, compact }: { caseId: string; refId: string; ev: EvidenceIndex | undefined; compact?: boolean }) {
  if (refId.startsWith('POL-')) {
    const [t, sm] = POLICY_INFO[refId.slice(0, 6)] ?? [refId, '']
    return (
      <p className="small" style={{ color: 'var(--ink-2)' }}>
        <strong style={{ color: 'var(--ink)' }}>{t}.</strong> {sm}
      </p>
    )
  }
  if (!ev) return <p className="small muted">Loading…</p>
  const item = ev[refId]
  if (!item) return <p className="small muted">Not part of this case file.</p>
  const d = item.data
  switch (item.kind) {
    case 'chat_message':
      return (
        <div className="bubbles">
          <div className={`bubble ${d.sender_role}`}>
            <div className="who">{d.sender_role === 'rider' ? 'Rider' : 'Driver'} · {clock(d.timestamp)}</div>
            {d.text}
          </div>
        </div>
      )
    case 'photo':
      return (
        <>
          <div className="photo"><img src={photoUrl(item)} alt="Photo evidence" /></div>
          {d.analysis && <p className="small" style={{ marginTop: 8 }}>{d.analysis.description}</p>}
        </>
      )
    case 'payment':
      return <Receipt data={d} />
    case 'route_comparison':
      return (
        <dl className="kv">
          <dt>Fastest route</dt><dd>{d.optimal_km.toFixed(2)} km</dd>
          <dt>Driven</dt><dd>{d.actual_km.toFixed(2)} km</dd>
          <dt>Extra</dt><dd>+{d.extra_km.toFixed(2)} km ({d.extra_pct.toFixed(1)}%)</dd>
          <dt>Refund if unexplained</dt><dd>{money(d.refund_if_unjustified)}</dd>
        </dl>
      )
    case 'pickup_proximity':
      return (
        <dl className="kv">
          <dt>Closest to pickup</dt><dd>{Math.round(d.closest_approach_m).toLocaleString()} m</dd>
          <dt>Arrival radius</dt><dd>{d.arrival_radius_m} m</dd>
          <dt>Reached pickup</dt><dd>{d.reached_pickup ? 'Yes' : 'No'}</dd>
        </dl>
      )
    case 'traffic_event':
      return (
        <dl className="kv">
          <dt>Type</dt><dd>{String(d.type).replaceAll('_', ' ')}</dd>
          {d.distance_to_planned_route_m != null && (
            <>
              <dt>From planned route</dt><dd>{d.distance_to_planned_route_m} m</dd>
              <dt>During the trip</dt><dd>{d.during_trip ? 'Yes' : 'No'}</dd>
            </>
          )}
        </dl>
      )
    case 'behavior_profile':
      return (
        <dl className="kv">
          <dt>Disputes, last 30 days</dt><dd>{d.dispute_count_30d}</dd>
          <dt>Account age</dt><dd>{d.account_age_days} days</dd>
        </dl>
      )
    case 'route':
    case 'gps_trace':
      return compact ? (
        <p className="small muted">
          {item.kind === 'route' ? `${Number(d.length_km).toFixed(2)} km` : `${d.length ?? d.points ?? ''} GPS fixes`}. Open to see the map.
        </p>
      ) : (
        <TripMap geo={geoFromEvidence(ev)} id={caseId} />
      )
    default:
      return null
  }
}

export function Cite({ caseId, refId, n }: { caseId: string; refId: string; n?: number }) {
  const ctx = useContext(EvidenceCtx)
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null)
  const ref = useRef<HTMLButtonElement>(null)
  const { data: ev } = useEvidence(pos ? caseId : null)
  const [label, icon] = refKind(refId)
  const show = () => {
    const r = ref.current!.getBoundingClientRect()
    const left = Math.min(Math.max(12, r.left), window.innerWidth - 312)
    const top = r.bottom + 8 + 260 > window.innerHeight ? Math.max(12, r.top - 8 - 240) : r.bottom + 8
    setPos({ left, top })
  }
  return (
    <button
      ref={ref}
      type="button"
      className={n ? 'fn' : `cite${refId.startsWith('POL-') ? ' policy' : ''}`}
      onMouseEnter={show}
      onMouseLeave={() => setPos(null)}
      onFocus={show}
      onBlur={() => setPos(null)}
      onClick={() => {
        setPos(null)
        ctx.open(caseId, refId)
      }}
      aria-label={`${label} ${refId}, open evidence`}
    >
      {n ? n : <><Icon name={icon} size={12} />{refId}</>}
      {pos && (
        <div className="popover" style={pos} role="tooltip">
          <div className="popover-title"><span>{label}</span><span className="mono">{refId}</span></div>
          <Preview caseId={caseId} refId={refId} ev={ev} compact />
        </div>
      )}
    </button>
  )
}

const MAP_KINDS = ['route', 'gps_trace', 'route_comparison', 'pickup_proximity', 'traffic_event']

function Drawer({ caseId, refId, onClose }: { caseId: string; refId: string; onClose: () => void }) {
  const { data: ev } = useEvidence(caseId)
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  const [label] = refKind(refId)
  const item = ev?.[refId]
  const isMap = item && MAP_KINDS.includes(item.kind)
  return (
    <div>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={`${label} ${refId}`}>
        <div className="drawer-head">
          <div>
            <p className="small muted">{label} · {caseId}</p>
            <h2 className="mono" style={{ fontSize: 20 }}>{refId}</h2>
          </div>
          <button className="close" onClick={onClose} aria-label="Close"><Icon name="x" size={16} /></button>
        </div>
        <div className="drawer-body">
          {isMap && ev && (
            <div className="sheet" style={{ border: '1px solid var(--hair)' }}><TripMap geo={geoFromEvidence(ev)} id={`d${caseId}`} /></div>
          )}
          {refId.startsWith('POL-') ? (
            <PolicyView refId={refId} />
          ) : item?.kind === 'chat_message' && ev ? (
            <Chat ev={ev} highlight={refId} />
          ) : (
            <Preview caseId={caseId} refId={refId} ev={ev} />
          )}
          <p className="tiny muted">
            {refId.startsWith('POL-')
              ? 'From the policy the agents search. Figures marked “not Ryde-sourced” are this project’s own rules.'
              : 'Exactly as it appears in the case file every agent worked from.'}
          </p>
        </div>
      </aside>
    </div>
  )
}

export function Chat({ ev, highlight }: { ev: EvidenceIndex; highlight?: string }) {
  const msgs = Object.entries(ev)
    .filter(([, e]) => e.kind === 'chat_message')
    .map(([k, e]) => ({ k, ...(e.data as { sender_role: 'rider' | 'driver'; timestamp: string; text: string }) }))
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp))
  if (!msgs.length) return <p className="small muted">No messages between rider and driver.</p>
  return (
    <div className="bubbles">
      {msgs.map((m) => (
        <div key={m.k} className={`bubble ${m.sender_role}${m.k === highlight ? ' hl' : ''}`}>
          <div className="who">
            <span>{m.sender_role === 'rider' ? 'Rider' : 'Driver'} · {clock(m.timestamp)}</span>
            <span className="mono">{m.k}</span>
          </div>
          {m.text}
        </div>
      ))}
    </div>
  )
}

export interface Fare {
  base_fare: number | string
  platform_fee: number | string
  taxes: number | string
  total_fare: number | string
  add_on_fees?: { type: string; amount: number }[] | null
}

export function Receipt({ data }: { data: Fare }) {
  return (
    <dl className="kv">
      <dt>Base fare</dt><dd>{money(data.base_fare)}</dd>
      <dt>Platform fee</dt><dd>{money(data.platform_fee)}</dd>
      <dt>Taxes</dt><dd>{money(data.taxes)}</dd>
      {(data.add_on_fees ?? []).map((f, i) => (
        <FeeRow key={i} label={f.type.replaceAll('_', ' ').replace(/^./, (c) => c.toUpperCase())} amount={f.amount} />
      ))}
      <dt style={{ color: 'var(--ink)', fontWeight: 600 }}>Total charged</dt>
      <dd style={{ fontWeight: 600 }}>{money(data.total_fare)}</dd>
    </dl>
  )
}

function FeeRow({ label, amount }: { label: string; amount: number }) {
  return (
    <>
      <dt>{label}</dt><dd>{money(amount)}</dd>
    </>
  )
}
