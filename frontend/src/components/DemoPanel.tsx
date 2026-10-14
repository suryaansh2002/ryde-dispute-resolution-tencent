import { useMemo, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { Category } from '../types/api'
import { first, money, outcomeLabel, statusPill } from '../lib/format'
import {
  buildSteps, caseSeconds, errorOf, isLit, outcomeIcon, STEP_EXPLAIN, STEP_ICON, stepTime, tokensOf,
} from '../lib/hearing'
import type { LiveCase } from '../lib/live'
import { Icon } from './Icon'

/* The hearing behind the phone, outside the app: the rider and driver apps never show
   the AI at work, so this panel does it for the demo. */

export function DemoPanel({
  caseId,
  live,
  category,
  waitingFor,
  actions,
}: {
  caseId: string | null
  live: LiveCase
  category: Category | null
  /** Name of the party whose reply the case is waiting on, if any. */
  waitingFor?: string | null
  actions?: ReactNode
}) {
  const { events, usage, state, decision } = live
  const steps = useMemo(() => {
    if (!caseId || !state) return buildSteps([], 'opened', category).map((s) => ({ ...s, status: 'idle' as const }))
    return buildSteps(events, state, category)
  }, [caseId, state, events, category])
  const failed = errorOf(events)
  const final = !!state && ['decided', 'escalated', 'safety_bypassed', 'declined_insufficient_evidence'].includes(state)
  const dec = decision?.decision
  const secs = caseSeconds(events)
  const tokens = tokensOf(usage)

  let lede: string
  if (!caseId) lede = 'Nothing is running yet. When the report is sent, each step of the hearing lights up here as it happens.'
  else if (failed) lede = 'Something failed on the server. The error is shown below and in the full trace.'
  else if (state === 'awaiting_response')
    lede = waitingFor
      ? `Paused: the case waits for ${first(waitingFor)}'s reply before the hearing starts.`
      : 'Paused: the case waits for the other side’s reply before the hearing starts.'
  else if (!final) lede = 'The hearing behind the phone, live.'
  else lede = 'The full hearing behind this outcome.'

  return (
    <aside className="demo-panel" aria-label="Behind the scenes" aria-live="polite">
      <div className="dp-head">
        <h2>Behind the scenes</h2>
        <span className="tag">Demo panel, not part of the app</span>
      </div>
      <p className="small muted">{lede}</p>
      <ol className="dp-steps">
        {steps.map((s) => {
          const cls = s.status === 'wait' ? 'idle' : s.status
          return (
            <li key={s.key} className={`dp-row ${s.kind} ${cls}`}>
              <span className="dp-ic">
                <Icon name={s.key === 'outcome' ? outcomeIcon(s.status) : STEP_ICON[s.key]} size={13} stroke={2.4} />
              </span>
              <span className="dp-l">
                {s.label}
                {s.status === 'now' && STEP_EXPLAIN[s.key] && <small>{STEP_EXPLAIN[s.key]}</small>}
                {s.status === 'wait' && <small>Starts when the other side replies.</small>}
              </span>
              <span className="dp-t">
                {isLit(s.status) && s.kind !== 'person'
                  ? stepTime(events, usage, s.key)
                  : s.kind === 'rule' ? 'no AI' : s.kind === 'ai' ? 'AI' : ''}
              </span>
            </li>
          )
        })}
      </ol>
      {failed && (
        <div className="dp-sum" role="alert">
          <span className="pill bad">Error</span>
          <p className="small" style={{ color: 'var(--ink-2)', wordBreak: 'break-word' }}>{failed.detail}</p>
        </div>
      )}
      {final && state && (
        <div className="dp-sum">
          <span className={`pill ${statusPill(state)[0]}`}>{statusPill(state)[1]}</span>
          {dec && (
            <p>
              <strong>{outcomeLabel(dec.outcome)}</strong>
              {dec.remedy?.amount ? ` · ${money(dec.remedy.amount)}` : ''}, confidence {dec.confidence.toFixed(2)}
            </p>
          )}
          <p className="small muted">
            {secs != null ? `${Math.round(secs)} s from report to outcome` : ''}
            {tokens ? ` · ${Math.round(tokens / 1000)}K tokens` : ''}
          </p>
        </div>
      )}
      {actions}
      {caseId && (
        <Link className="btn btn-secondary btn-sm" style={{ alignSelf: 'flex-start' }} to={`/trace/${caseId}`}>
          <Icon name="activity" size={14} />
          Open the full hearing
        </Link>
      )}
    </aside>
  )
}
