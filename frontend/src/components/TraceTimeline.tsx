import type { ReactNode } from 'react'
import { Ref } from '../lib/evidence'
import { CATEGORY_LABEL, STATE_LABEL, clock } from '../lib/format'
import { strippedRefs } from '../lib/strip'
import type {
  Argument,
  CaseFile,
  CaseState,
  Category,
  DecisionObject,
  DamageFinding,
  TraceEvent,
  TriageResult,
} from '../types/api'
import { ArgumentCard } from './ArgumentCard'
import { PhotoFinding } from './PhotoFinding'
import { Ruling } from './Ruling'

const seconds = (ms?: number | null) => (ms ? `${(ms / 1000).toFixed(1)} s` : null)

function Item({ event, children }: { event: TraceEvent; children: ReactNode }) {
  return (
    <div className="tl-item">
      <span className="tl-time">{clock(event.t)}</span>
      <div className="stack" style={{ gap: 6 }}>
        {children}
      </div>
    </div>
  )
}

function Diamond() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden style={{ flex: 'none' }}>
      <rect x="2.5" y="2.5" width="7" height="7" transform="rotate(45 6 6)" fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  )
}

function TriageCard({ result, latency }: { result: TriageResult; latency?: number | null }) {
  return (
    <article className="card system">
      <div className="card-head">
        <span className="agent-label">Triage agent</span>
        {seconds(latency) && <span className="tiny faint mono">{seconds(latency)}</span>}
      </div>
      <div className="row">
        <span className="badge">{CATEGORY_LABEL[result.category] ?? result.category}</span>
        <span className="badge">severity: {result.tier}</span>
        <span className={`badge ${result.is_safety ? 'tone-bad' : ''}`}>
          {result.is_safety ? 'Safety flag: a person takes over' : 'No safety concern'}
        </span>
      </div>
    </article>
  )
}

function EvidenceCard({ caseFile, latency }: { caseFile: CaseFile; latency?: number | null }) {
  const counts = [
    [caseFile.chat_log?.length ?? 0, 'chat messages'],
    [caseFile.gps_trace?.length ?? 0, 'GPS fixes'],
    [caseFile.photos?.length ?? 0, 'photos'],
    [caseFile.traffic_events?.length ?? 0, 'traffic events'],
  ] as const
  const policies = [...new Set((caseFile.policy_tags ?? []).map((t) => t.chunk_id))]
  const keyRefs = ['ROUTE-COMPARISON', 'PICKUP-PROXIMITY', 'PAYMENT']
  return (
    <article className="card system">
      <div className="card-head">
        <span className="agent-label">Evidence collection agent</span>
        {seconds(latency) && <span className="tiny faint mono">{seconds(latency)}</span>}
      </div>
      <p className="small">
        Case file assembled from the trip record:{' '}
        {counts.map(([n, label], i) => (
          <span key={label}>
            <strong className="num">{n}</strong> {label}
            {i < counts.length - 1 ? ', ' : '.'}
          </span>
        ))}
      </p>
      <div className="refs">
        {keyRefs.map((r) => (
          <Ref key={r} id={r} />
        ))}
        {(caseFile.photos ?? []).map((p) => (
          <Ref key={p.evidence_id} id={p.evidence_id} />
        ))}
        {policies.map((p) => (
          <Ref key={p} id={p} />
        ))}
      </div>
    </article>
  )
}

/** "prevention: pass — ..." / "escalation gate: bucket=..., ..." → readable rule outcome. */
function RuleLine({ detail }: { detail: string }) {
  let label = detail
  let tone = ''
  if (detail.startsWith('prevention:')) {
    const action = detail.replace('prevention: ', '').split(' — ')[0].split(' (')[0]
    const rest = detail.includes(' — ') ? detail.split(' — ').slice(1).join(' — ') : ''
    const pass = action === 'pass'
    tone = pass ? '' : 'tone-warn'
    label = pass
      ? `Prevention rules: all six passed${detail.includes('repeat filer') ? ', repeat filer flagged for the gate' : ''}`
      : `Prevention rules: ${action.replaceAll('_', ' ')}${rest ? `, ${rest}` : ''}`
  } else if (detail.startsWith('escalation gate:')) {
    const flagged = /bucket=always_escalate|confidence_escalate=True|judge_requested=True|veto/.test(detail)
    tone = flagged ? 'tone-warn' : ''
    label = flagged
      ? 'Escalation gate and compliance: flagged, so the decision goes to a person'
      : 'Escalation gate and compliance: all passed'
  }
  return (
    <div className={`gate-line ${tone}`} title={detail}>
      <Diamond />
      <span>{label}</span>
      <span className="tiny faint" style={{ marginLeft: 'auto', whiteSpace: 'nowrap' }}>
        no model
      </span>
    </div>
  )
}

type Block = { kind: 'single'; event: TraceEvent } | { kind: 'advocates'; events: TraceEvent[] }

const isAdvocate = (e: TraceEvent) =>
  e.kind === 'agent_output' && (e.agent === 'rider_advocate' || e.agent === 'driver_advocate')

/** Consecutive rider/driver outputs render side by side: the symmetric hearing. */
function group(events: TraceEvent[]): Block[] {
  const blocks: Block[] = []
  for (const event of events) {
    const last = blocks[blocks.length - 1]
    if (isAdvocate(event) && last?.kind === 'advocates' && last.events.length < 2) last.events.push(event)
    else if (isAdvocate(event)) blocks.push({ kind: 'advocates', events: [event] })
    else blocks.push({ kind: 'single', event })
  }
  return blocks
}

function renderEvent(e: TraceEvent, category: Category | null): ReactNode {
  switch (e.kind) {
    case 'state_transition': {
      const to = e.detail?.includes('->') ? (e.detail.split('->')[1].trim() as CaseState) : null
      return (
        <div className="tl-line">
          {to ? (
            <>
              → <strong>{STATE_LABEL[to] ?? to}</strong>
            </>
          ) : (
            <strong>{e.detail === 'response received' ? 'The other side responded' : e.detail}</strong>
          )}
        </div>
      )
    }
    case 'rule_evaluation':
      return <RuleLine detail={e.detail ?? ''} />
    case 'agent_output':
      if (e.agent === 'triage') return <TriageCard result={e.output as unknown as TriageResult} latency={e.latency_ms} />
      if (e.agent === 'evidence_collection')
        return <EvidenceCard caseFile={e.output as unknown as CaseFile} latency={e.latency_ms} />
      if (e.agent === 'judge')
        return (
          <>
            <div className="agent-label" style={{ paddingTop: 2 }}>
              Judge {seconds(e.latency_ms) && <span className="tiny faint mono">· {seconds(e.latency_ms)}</span>}
            </div>
            <Ruling
              decision={e.output as unknown as DecisionObject}
              category={category}
              title="Judge’s ruling"
              stripped={strippedRefs(e.detail)}
            />
          </>
        )
      return <div className="tl-line">{e.agent} output</div>
    case 'tool_call': {
      const findings = ((e.output as { findings?: Record<string, DamageFinding> } | null)?.findings ?? {})
      return (
        <article className="card system">
          <div className="card-head">
            <span className="agent-label">Image analysis</span>
            <span className="tiny faint">
              vision tool{seconds(e.latency_ms) && ` · ${seconds(e.latency_ms)}`}
            </span>
          </div>
          <div className="stack" style={{ gap: 10 }}>
            {Object.entries(findings).map(([ref, f]) => (
              <PhotoFinding key={ref} id={ref} finding={f} />
            ))}
            {Object.keys(findings).length === 0 && <p className="small muted">{e.detail}</p>}
          </div>
          <p className="tiny faint" style={{ marginTop: 8 }}>
            The model says what it sees; the tier comes from the policy’s tier table, in code. Both advocates and the
            Judge get this same finding.
          </p>
        </article>
      )
    }
    case 'escalation':
      return (
        <div className="banner tone-warn" style={{ margin: 0 }}>
          <strong>Sent to the human review queue.</strong> A reviewer will ratify or override it.
        </div>
      )
    case 'l2_review':
      return (
        <>
          <div className="banner tone-good" style={{ margin: 0 }}>
            <span>
              <strong>Human review:</strong> {e.detail}
            </span>
          </div>
          {e.output && (
            <Ruling decision={e.output as unknown as DecisionObject} category={category} title="Final decision" gates={false} />
          )}
        </>
      )
    case 'error':
      return (
        <div className="banner tone-bad" style={{ margin: 0 }}>
          <span>
            <strong>Pipeline error.</strong> {e.detail}
          </span>
        </div>
      )
    default:
      return (
        <div className="tl-line">
          {e.kind}: {e.detail}
        </div>
      )
  }
}

export function TraceTimeline({
  events,
  working,
  category,
}: {
  events: TraceEvent[]
  working?: boolean
  category: Category | null
}) {
  if (events.length === 0)
    return (
      <div className="empty">
        <span className="spinner" /> Waiting for the first trace event…
      </div>
    )
  return (
    <div className="timeline">
      {group(events).map((block) =>
        block.kind === 'single' ? (
          <Item key={block.event.id} event={block.event}>
            {renderEvent(block.event, category)}
          </Item>
        ) : (
          <Item key={block.events[0].id} event={block.events[0]}>
            <div className="versus">
              {[...block.events]
                .sort((a, b) => Number(b.agent === 'rider_advocate') - Number(a.agent === 'rider_advocate'))
                .map((e) => (
                  <ArgumentCard key={e.id} argument={e.output as unknown as Argument} note={e.detail} />
                ))}
            </div>
            <div className="tiny faint">
              Both advocates argued in parallel from the identical case file
              {seconds(block.events[0].latency_ms) && ` · ${seconds(block.events[0].latency_ms)}`}
            </div>
          </Item>
        ),
      )}
      {working && (
        <div className="tl-item">
          <span />
          <div className="tl-line row">
            <span className="spinner" /> working…
          </div>
        </div>
      )}
    </div>
  )
}
