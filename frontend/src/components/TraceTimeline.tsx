import type { ReactNode } from 'react'
import { CATEGORY_LABEL } from '../lib/format'
import type {
  Argument,
  CaseFile,
  DecisionObject,
  TraceEvent,
  TriageResult,
} from '../types/api'
import { ArgumentCard } from './ArgumentCard'
import { DecisionCard } from './DecisionCard'

const time = (iso: string) =>
  new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' })

const seconds = (ms?: number | null) => (ms ? ` · ${(ms / 1000).toFixed(1)}s` : '')

function Item({ event, children }: { event: TraceEvent; children: ReactNode }) {
  return (
    <div className="tl-item">
      <span className="tl-time">{time(event.t)}</span>
      <div>{children}</div>
    </div>
  )
}

function TriageCard({ result }: { result: TriageResult }) {
  return (
    <article className="agent-card intake">
      <header>
        <span className="agent-name">Triage agent</span>
      </header>
      <div className="row">
        <span className="badge tone-progress">{CATEGORY_LABEL[result.category] ?? result.category}</span>
        <span className="badge">tier: {result.tier}</span>
        <span className={`badge ${result.is_safety ? 'tone-bad' : 'tone-neutral'}`}>
          {result.is_safety ? 'safety flag → human review' : 'no safety flag'}
        </span>
      </div>
    </article>
  )
}

function EvidenceCard({ caseFile, latency }: { caseFile: CaseFile; latency?: number | null }) {
  const counts = [
    `${caseFile.chat_log?.length ?? 0} chat messages`,
    `${caseFile.gps_trace?.length ?? 0} GPS points`,
    `${caseFile.photos?.length ?? 0} photos`,
    `${caseFile.traffic_events?.length ?? 0} traffic events`,
  ]
  const policies = [...new Set((caseFile.policy_tags ?? []).map((t) => t.policy_id))]
  return (
    <article className="agent-card intake">
      <header>
        <span className="agent-name">Evidence collection agent</span>
        <span className="small muted">case file assembled{seconds(latency)}</span>
      </header>
      <p className="small">{counts.join(' · ')}</p>
      {policies.length > 0 && (
        <div className="refs">
          <span className="small muted">Policy tagged:</span>
          {policies.map((p) => (
            <span key={p} className="chip">
              {p}
            </span>
          ))}
        </div>
      )}
    </article>
  )
}

type Block =
  | { kind: 'single'; event: TraceEvent }
  | { kind: 'advocates'; events: TraceEvent[] }

const isAdvocate = (e: TraceEvent) =>
  e.kind === 'agent_output' && (e.agent === 'rider_advocate' || e.agent === 'driver_advocate')

/** Consecutive rider/driver outputs render side by side: the symmetric hearing. */
function group(events: TraceEvent[]): Block[] {
  const blocks: Block[] = []
  for (const event of events) {
    const last = blocks[blocks.length - 1]
    if (isAdvocate(event) && last?.kind === 'advocates' && last.events.length < 2) {
      last.events.push(event)
    } else if (isAdvocate(event)) {
      blocks.push({ kind: 'advocates', events: [event] })
    } else {
      blocks.push({ kind: 'single', event })
    }
  }
  return blocks
}

function renderEvent(e: TraceEvent): ReactNode {
  switch (e.kind) {
    case 'state_transition':
      return (
        <div className="tl-line">
          {e.detail?.includes('->') ? (
            <>
              state: <strong>{e.detail.split('->')[1].trim().replaceAll('_', ' ')}</strong>
            </>
          ) : (
            <strong>{e.detail}</strong>
          )}
        </div>
      )
    case 'rule_evaluation':
      return <div className="tl-line mono">{e.detail}</div>
    case 'agent_output':
      if (e.agent === 'triage') return <TriageCard result={e.output as unknown as TriageResult} />
      if (e.agent === 'evidence_collection')
        return <EvidenceCard caseFile={e.output as unknown as CaseFile} latency={e.latency_ms} />
      if (e.agent === 'judge')
        return <DecisionCard decision={e.output as unknown as DecisionObject} />
      return <div className="tl-line">{e.agent} output</div>
    case 'escalation':
      // The Judge's card above already lists the reasons; don't print them twice.
      return (
        <div className="callout tone-warn">
          <strong>Routed to the L2 human queue</strong> for a person to ratify or override.
        </div>
      )
    case 'l2_review':
      return (
        <div className="stack">
          <div className="callout tone-good">
            <strong>L2 review:</strong> {e.detail}
          </div>
          {e.output && (
            <DecisionCard decision={e.output as unknown as DecisionObject} title="Final decision" />
          )}
        </div>
      )
    case 'error':
      return (
        <div className="callout tone-bad">
          <strong>Pipeline error.</strong> {e.detail}
        </div>
      )
    default:
      return <div className="tl-line">{e.kind}: {e.detail}</div>
  }
}

export function TraceTimeline({ events, working }: { events: TraceEvent[]; working?: boolean }) {
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
            {renderEvent(block.event)}
          </Item>
        ) : (
          <Item key={block.events[0].id} event={block.events[0]}>
            <div className="versus">
              {[...block.events]
                .sort((a, b) => Number(b.agent === 'rider_advocate') - Number(a.agent === 'rider_advocate'))
                .map((e) => (
                  <ArgumentCard
                    key={e.id}
                    argument={e.output as unknown as Argument}
                    note={e.detail}
                  />
                ))}
            </div>
            <div className="small faint" style={{ marginTop: 4 }}>
              Both advocates argued from the identical case file, in parallel{seconds(block.events[0].latency_ms)}
            </div>
          </Item>
        ),
      )}
      {working && (
        <div className="tl-item">
          <span />
          <div className="tl-line">
            <span className="spinner" /> working…
          </div>
        </div>
      )}
    </div>
  )
}
