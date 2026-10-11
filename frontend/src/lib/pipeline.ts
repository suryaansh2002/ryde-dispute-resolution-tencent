import type { DecisionObject, TraceEvent } from '../types/api'

/**
 * The case's route through the system, derived from its trace events. Agents are
 * circles on the map; deterministic rules (no model) are diamonds. Order is the real
 * order of the pipeline (system design §6).
 */
export type StationId =
  | 'claim'
  | 'triage'
  | 'prevention'
  | 'evidence'
  | 'response'
  | 'rider'
  | 'driver'
  | 'judge'
  | 'gate'
  | 'compliance'
  | 'outcome'

export type StationKind = 'agent' | 'rule' | 'human' | 'endpoint'
export type StationStatus = 'idle' | 'active' | 'done' | 'flagged' | 'stopped' | 'skipped'

export interface Station {
  id: StationId
  label: string
  kind: StationKind
  status: StationStatus
  note?: string
}

export const STATION_DEFS: { id: StationId; label: string; kind: StationKind }[] = [
  { id: 'claim', label: 'Claim', kind: 'endpoint' },
  { id: 'triage', label: 'Triage', kind: 'agent' },
  { id: 'prevention', label: 'Prevention rules', kind: 'rule' },
  { id: 'evidence', label: 'Evidence', kind: 'agent' },
  { id: 'response', label: 'Other side responds', kind: 'human' },
  { id: 'rider', label: 'Rider advocate', kind: 'agent' },
  { id: 'driver', label: 'Driver advocate', kind: 'agent' },
  { id: 'judge', label: 'Judge', kind: 'agent' },
  { id: 'gate', label: 'Escalation gate', kind: 'rule' },
  { id: 'compliance', label: 'Compliance', kind: 'rule' },
  { id: 'outcome', label: 'Outcome', kind: 'endpoint' },
]

const toState = (e: TraceEvent) =>
  e.kind === 'state_transition' && e.detail?.includes('->') ? e.detail.split('->')[1].trim() : null

export function deriveStations(events: TraceEvent[]): Station[] {
  const st: Record<StationId, Station> = Object.fromEntries(
    STATION_DEFS.map((d) => [d.id, { ...d, status: 'idle' as StationStatus }]),
  ) as Record<StationId, Station>
  const set = (id: StationId, status: StationStatus, note?: string) => {
    st[id] = { ...st[id], status, note: note ?? st[id].note }
  }
  const agentDone = (agent: string) =>
    events.some((e) => e.kind === 'agent_output' && e.agent === agent)

  if (events.length) set('claim', 'done')
  for (const e of events) {
    const to = toState(e)
    if (to === 'triage') set('triage', 'active')
    if (e.kind === 'agent_output' && e.agent === 'triage') {
      set('triage', 'done')
      set('prevention', 'active')
    }
    if (e.kind === 'rule_evaluation' && e.detail?.startsWith('prevention')) {
      const passed = e.detail.includes('prevention: pass')
      set('prevention', passed ? 'done' : 'stopped', passed ? undefined : e.detail.replace('prevention: ', ''))
    }
    if (to === 'assembling') set('evidence', 'active')
    if (e.kind === 'agent_output' && e.agent === 'evidence_collection') set('evidence', 'done')
    if (to === 'awaiting_response') set('response', 'active', 'waiting')
    if (e.kind === 'state_transition' && e.detail === 'response received') set('response', 'done', '')
    if (to === 'adjudicating') {
      if (st.response.status !== 'done') set('response', 'skipped', 'no response')
      if (!agentDone('rider_advocate')) set('rider', 'active')
      if (!agentDone('driver_advocate')) set('driver', 'active')
    }
    if (e.kind === 'agent_output' && e.agent === 'rider_advocate') set('rider', 'done')
    if (e.kind === 'agent_output' && e.agent === 'driver_advocate') set('driver', 'done')
    if (
      e.kind === 'agent_output' &&
      (e.agent === 'rider_advocate' || e.agent === 'driver_advocate') &&
      agentDone('rider_advocate') &&
      agentDone('driver_advocate') &&
      !agentDone('judge')
    )
      set('judge', 'active')
    if (e.kind === 'agent_output' && e.agent === 'judge') {
      set('judge', 'done')
      const d = e.output as unknown as DecisionObject
      const esc = d.escalation
      const flagged = esc.bucket_escalate || esc.confidence_escalate || esc.judge_requested_escalation
      set('gate', flagged ? 'flagged' : 'done', flagged ? 'to human review' : 'cleared')
      set('compliance', esc.compliance_veto ? 'flagged' : 'done', esc.compliance_veto ? 'veto' : 'pass')
    }
    if (to === 'safety_bypassed') set('outcome', 'flagged', 'safety → human')
    if (to === 'declined_insufficient_evidence') set('outcome', 'stopped', 'declined')
    if (to === 'escalated') set('outcome', 'flagged', 'human review')
    if (to === 'decided') set('outcome', 'done', 'decided')
    if (e.kind === 'error') {
      const active = Object.values(st).find((s) => s.status === 'active')
      if (active) set(active.id, 'stopped', 'error')
    }
  }
  return STATION_DEFS.map((d) => st[d.id])
}

/** Plain-language narration of whatever is happening now: the demo's captions. */
export const STAGE_CAPTION: Partial<Record<StationId, { title: string; text: string }>> = {
  triage: {
    title: 'Triage agent',
    text: 'Reads the claim in the filer’s own words and decides the category, the severity and whether it is a safety matter. Safety matters leave the automated system here.',
  },
  prevention: {
    title: 'Prevention rules',
    text: 'Six deterministic checks, no model: duplicate claim, malformed request, safety hard-stop, required evidence, repeat filer, 30-day window. Rejected claims cost nothing.',
  },
  evidence: {
    title: 'Evidence collection agent',
    text: 'The only agent allowed to touch raw data. It assembles one case file (GPS trace, planned vs driven route, fare, chat log, photos, both parties’ history) and every item gets a citable reference.',
  },
  response: {
    title: 'The other side responds',
    text: 'The person the claim is against gets to tell their side before anyone decides. Their words go to the advocates, never to the Judge.',
  },
  rider: {
    title: 'Two advocates, one case file',
    text: 'A rider advocate and a driver advocate argue in parallel from the identical case file. Every factual claim must cite evidence; uncited claims are stripped by a validator.',
  },
  driver: {
    title: 'Two advocates, one case file',
    text: 'A rider advocate and a driver advocate argue in parallel from the identical case file. Every factual claim must cite evidence; uncited claims are stripped by a validator.',
  },
  judge: {
    title: 'Judge agent',
    text: 'Weighs both arguments against the case file and the policy. It never sees the original complaint. Dollar amounts come from the policy formula, computed in code.',
  },
  outcome: {
    title: 'Gates, then the outcome',
    text: 'A deterministic escalation gate (confidence, risk bucket) and a compliance check run on every decision. Anything they flag goes to a human reviewer instead of being final.',
  },
}

export function currentStation(stations: Station[]): Station | null {
  return stations.find((s) => s.status === 'active') ?? null
}

const STATE_REACHED: Record<string, StationId[]> = {
  opened: ['claim'],
  triage: ['claim'],
  assembling: ['claim', 'triage', 'prevention'],
  awaiting_response: ['claim', 'triage', 'prevention', 'evidence'],
  adjudicating: ['claim', 'triage', 'prevention', 'evidence', 'response'],
  decided: STATION_DEFS.map((d) => d.id),
  escalated: STATION_DEFS.map((d) => d.id).filter((id) => id !== 'outcome'),
  safety_bypassed: ['claim', 'triage'],
  declined_insufficient_evidence: ['claim', 'triage'],
}

/** A coarse picture from the case state alone, for before the trace stream has replayed. */
export function stationsFromState(state: string): Station[] {
  const reached = new Set(STATE_REACHED[state] ?? [])
  return STATION_DEFS.map((d) => ({
    ...d,
    status: reached.has(d.id)
      ? 'done'
      : d.id === 'outcome' && (state === 'escalated' || state === 'safety_bypassed')
        ? 'flagged'
        : d.id === 'prevention' && state === 'declined_insufficient_evidence'
          ? 'stopped'
          : 'idle',
  }))
}
