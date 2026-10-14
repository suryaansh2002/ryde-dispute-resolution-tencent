import type { AgentName, Argument, CaseState, Category, DamageFinding, DecisionObject, TraceEvent, TriageResult, UsageRow } from '../types/api'
import { secondsBetween, secs } from './format'

// The case as a hearing, derived from its trace events. Works on a finished case and on
// one that is still running: steps that haven't happened yet are laid out from what the
// pipeline will do next, and each step lights up when its event arrives.

export type StepKey = 'report' | 'triage' | 'rules' | 'evidence' | 'photo' | 'hearing' | 'judge' | 'gates' | 'outcome'
export type StepKind = 'person' | 'ai' | 'rule'
export type StepStatus = 'done' | 'now' | 'idle' | 'flag' | 'stop' | 'wait'

export interface Step {
  key: StepKey
  label: string
  kind: StepKind
  status: StepStatus
}

export const agentEvent = (events: TraceEvent[], agent: AgentName) =>
  events.find((e) => e.kind === 'agent_output' && e.agent === agent)
export const agentOut = <T>(events: TraceEvent[], agent: AgentName) =>
  agentEvent(events, agent)?.output as T | undefined

export const triageOf = (events: TraceEvent[]) => agentOut<TriageResult>(events, 'triage')
export const argumentOf = (events: TraceEvent[], agent: 'rider_advocate' | 'driver_advocate') =>
  agentOut<Argument>(events, agent)
export const preventionOf = (events: TraceEvent[]) =>
  events.find((e) => e.kind === 'rule_evaluation' && (e.detail ?? '').startsWith('prevention'))
export const photoToolOf = (events: TraceEvent[]) =>
  events.find((e) => e.kind === 'tool_call' && (e.output as { tool?: string } | null)?.tool === 'image_analysis')
export const photoFindings = (events: TraceEvent[]) =>
  ((photoToolOf(events)?.output as { findings?: Record<string, DamageFinding> } | undefined)?.findings) ?? {}
export const errorOf = (events: TraceEvent[]) => events.find((e) => e.kind === 'error')

const FINAL: CaseState[] = ['decided', 'escalated', 'safety_bypassed', 'declined_insufficient_evidence']

export const OUTCOME_STEP: Partial<Record<CaseState, [string, StepStatus]>> = {
  decided: ['Judgment', 'done'],
  escalated: ['Referred', 'flag'],
  safety_bypassed: ['Safety team', 'flag'],
  declined_insufficient_evidence: ['Declined', 'stop'],
}

export function buildSteps(events: TraceEvent[], state: CaseState, category: Category | null): Step[] {
  const has = (agent: AgentName) => !!agentEvent(events, agent)
  const started = (agent: AgentName) => events.some((e) => e.kind === 'agent_start' && e.agent === agent)
  const prevention = preventionOf(events)
  const tool = photoToolOf(events)
  const triage = triageOf(events)
  const final = FINAL.includes(state)
  const stopped = !!prevention && !(prevention.detail ?? '').startsWith('prevention: pass')
  const cat = triage?.category ?? category
  // A safety flag at triage, or a decline before evidence, ends the case at the rules.
  const endsAtRules = stopped || (final && !has('evidence_collection'))

  const steps: Step[] = [
    { key: 'report', label: 'Complaint', kind: 'person', status: 'done' },
    {
      key: 'triage', label: 'Intake', kind: 'ai',
      status: triage ? 'done' : state === 'triage' || started('triage') || state === 'opened' ? 'now' : 'idle',
    },
    {
      key: 'rules', label: "Clerk's checks", kind: 'rule',
      status: prevention ? (stopped ? (state === 'safety_bypassed' ? 'flag' : 'stop') : 'done') : 'idle',
    },
  ]
  if (!endsAtRules) {
    const evidenceDone = has('evidence_collection')
    steps.push({
      key: 'evidence', label: 'Exhibits', kind: 'ai',
      status: evidenceDone ? 'done' : state === 'assembling' ? 'now' : 'idle',
    })
    if (tool || (cat === 'property_damage' && !final)) {
      steps.push({
        key: 'photo', label: 'Photo examined', kind: 'ai',
        status: tool ? 'done' : evidenceDone && state === 'assembling' ? 'now' : 'idle',
      })
    }
    const argued = has('rider_advocate') && has('driver_advocate')
    const ruled = has('judge')
    if (argued || !final) {
      steps.push(
        {
          key: 'hearing', label: 'Counsel', kind: 'ai',
          status: argued ? 'done' : state === 'adjudicating' ? 'now' : state === 'awaiting_response' ? 'wait' : 'idle',
        },
        { key: 'judge', label: 'The bench', kind: 'ai', status: ruled ? 'done' : argued ? 'now' : 'idle' },
        { key: 'gates', label: 'Final checks', kind: 'rule', status: ruled && final ? 'done' : ruled ? 'now' : 'idle' },
      )
    }
  }
  const [label, status] = OUTCOME_STEP[state] ?? ['Outcome', 'idle']
  steps.push({ key: 'outcome', label, kind: 'person', status })
  return steps
}

export const isLit = (s: StepStatus) => s === 'done' || s === 'flag' || s === 'stop'

/** How long each step took, from the usage log and the trace timings. */
export function stepTime(events: TraceEvent[], usage: UsageRow[], key: StepKey): string {
  const u = (agent: string) => {
    const rows = usage.filter((r) => r.agent === agent)
    return rows.length ? secs(rows.reduce((t, r) => t + (r.latency_ms ?? 0), 0)) : ''
  }
  switch (key) {
    case 'triage':
      return u('triage')
    case 'evidence':
      return u('evidence_collection')
    case 'photo':
      return secs(photoToolOf(events)?.latency_ms)
    case 'hearing':
      return secs(agentEvent(events, 'rider_advocate')?.latency_ms)
    case 'judge':
      return secs(agentEvent(events, 'judge')?.latency_ms)
    case 'rules':
    case 'gates':
      return 'no AI'
    default:
      return ''
  }
}

/** Seconds from the first event to the last state change. */
export function caseSeconds(events: TraceEvent[]): number | null {
  if (!events.length) return null
  const transitions = events.filter((e) => e.kind === 'state_transition')
  const end = transitions[transitions.length - 1]
  return end ? secondsBetween(events[0].t, end.t) : null
}

export const tokensOf = (usage: UsageRow[]) => usage.reduce((a, u) => a + u.input_tokens + u.output_tokens, 0)

export interface AgentUsage {
  i: number
  o: number
  r: number
  t: number
  ms: number
  model: string | null
}
export function agentUsage(usage: UsageRow[], agent: string): AgentUsage | null {
  const rows = usage.filter((u) => u.agent === agent)
  if (!rows.length) return null
  return rows.reduce<AgentUsage>(
    (a, x) => ({
      i: a.i + x.input_tokens, o: a.o + x.output_tokens, r: a.r + x.requests,
      t: a.t + x.tool_calls, ms: a.ms + (x.latency_ms ?? 0), model: x.model ?? a.model,
    }),
    { i: 0, o: 0, r: 0, t: 0, ms: 0, model: null },
  )
}

export const STEP_ICON: Record<Exclude<StepKey, 'outcome'>, 'msg' | 'list' | 'check' | 'file' | 'camera' | 'scale' | 'gavel'> = {
  report: 'msg',
  triage: 'list',
  rules: 'check',
  evidence: 'file',
  photo: 'camera',
  hearing: 'scale',
  judge: 'gavel',
  gates: 'check',
}
export const outcomeIcon = (s: StepStatus) => (s === 'done' ? 'check' : s === 'stop' ? 'x' : 'user')

export const STEP_EXPLAIN: Partial<Record<StepKey, string>> = {
  report: 'The person’s own words. They go to both counsel, never to the bench.',
  triage: 'An agent reads the report and files it: kind of dispute, severity, safety.',
  rules: 'Six plain-code checks. A failure stops the case here, before any further AI runs.',
  evidence: 'The only agent allowed to read raw records enters the exhibits.',
  photo: 'A vision call says what the photo shows. Code maps that to the fee tier.',
  hearing: 'Two counsel argue in parallel from the identical exhibits.',
  judge: 'The bench rules from the arguments and exhibits, citing every finding.',
  gates: 'Plain-code checks decide whether the ruling can stand without a person.',
}

/** The four plain-code checks a ruling has to pass to stand without a person:
 * [passed, name, detail]. */
export function gateChecks(dec: DecisionObject): [boolean, string, string][] {
  const e = dec.escalation
  return [
    [!e.confidence_escalate, 'Confidence at least 0.60', e.confidence_escalate ? `${dec.confidence.toFixed(2)}, too low to stand alone` : dec.confidence.toFixed(2)],
    [!e.bucket_escalate, 'Risk bucket', e.bucket_escalate ? (e.reasons?.find((r) => r.startsWith('bucket')) ?? '').replace(/^bucket: \w+ — /, '') : 'Not repeat, high-value or safety'],
    [!e.judge_requested_escalation, 'The bench’s own request', e.judge_requested_escalation ? 'The Judge asked for a person' : 'Not requested'],
    [!e.compliance_veto, 'Compliance', e.compliance_veto ? e.compliance_veto : 'Remedy matches the policy'],
  ]
}

/** The opening sentence of an argument or finding, for one-line previews. */
export function firstSentence(text: string, max = 200) {
  const s = text.split(/(?<=[.!?])\s+(?=[A-Z“"(])/)[0]?.trim() ?? text
  return s.length > max ? `${s.slice(0, max - 1).trimEnd()}…` : s
}
