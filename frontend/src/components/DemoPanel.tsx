import { useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { CaseState, Category, DamageFinding } from '../types/api'
import { CAT_FULL, first, money, outcomeLabel, REMEDY, secs as fmtSecs, statusPill } from '../lib/format'
import {
  agentEvent, agentUsage, argumentOf, buildSteps, caseSeconds, errorOf, firstSentence, gateChecks,
  isLit, outcomeIcon, photoFindings, preventionOf, STEP_EXPLAIN, STEP_ICON, stepTime, tokensOf,
  triageOf, type StepKey,
} from '../lib/hearing'
import type { LiveCase } from '../lib/live'
import { useEvidence } from '../lib/live'
import { Cite } from './evidence'
import { Icon } from './Icon'

const FEE: Record<string, number> = { minor: 40, moderate: 120, severe: 200 }

const OUTCOME_NOTE: Partial<Record<CaseState, string>> = {
  decided: 'Every final check passed, so the ruling stands without a person.',
  escalated: 'A final check flagged it, so the ruling waits in the support console for a person.',
  safety_bypassed: 'No agent heard this case. A safety specialist handles it from the support console.',
  declined_insufficient_evidence: 'Declined, not denied: the claimant was told what was missing and can refile.',
}

/** What one finished step did, from the case's own trace, for the expandable row. */
function StepDetail({ step, caseId, live }: { step: StepKey; caseId: string; live: LiveCase }) {
  const { events, usage, view, state } = live
  const dec = live.decision?.decision
  const { data: ev } = useEvidence(step === 'evidence' ? caseId : null)
  const model = (agent: string) => {
    const u = agentUsage(usage, agent)
    return u ? <p className="dp-meta">{u.model ?? 'model'} · {fmtSecs(u.ms)} · {Math.round((u.i + u.o) / 100) / 10}K tokens</p> : null
  }
  switch (step) {
    case 'report':
      return (
        <>
          <p>“{view?.claim_text}”</p>
          {view?.response && <p><span className="muted">Reply:</span> “{view.response.text}”</p>}
        </>
      )
    case 'triage': {
      const t = triageOf(events)
      return t ? (
        <>
          <p>Filed as {CAT_FULL[t.category].toLowerCase()}, {t.tier} severity. {t.is_safety ? 'Safety flag: goes straight to a person.' : 'No safety concern.'}</p>
          {model('triage')}
        </>
      ) : null
    }
    case 'rules': {
      const p = preventionOf(events)?.detail ?? ''
      return (
        <p>
          {p.startsWith('prevention: pass')
            ? `All six checks passed: not a duplicate, well formed, not safety, evidence present, within 30 days${p.includes('repeat filer') ? '. The filer has 3+ disputes in 30 days, which is noted for the final checks' : ''}.`
            : p.includes('safety')
              ? 'Safety hard stop: no agent hears this case.'
              : 'Required evidence missing: declined, not denied.'}
        </p>
      )
    }
    case 'evidence': {
      const out = agentEvent(events, 'evidence_collection')?.output as { chat_log?: unknown[]; gps_trace?: unknown[]; photos?: unknown[] } | undefined
      return (
        <>
          {out && <p>{out.gps_trace?.length ?? 0} GPS fixes, {out.chat_log?.length ?? 0} messages, {out.photos?.length ?? 0} photo{out.photos?.length === 1 ? '' : 's'}, the fare and both histories.</p>}
          {ev && <div className="dp-cites">{Object.keys(ev).map((r) => <Cite key={r} caseId={caseId} refId={r} />)}</div>}
          {model('evidence_collection')}
        </>
      )
    }
    case 'photo':
      return (
        <>
          {Object.entries(photoFindings(events)).map(([ref, f]: [string, DamageFinding]) => (
            <p key={ref}>
              {f.description} <span className="muted">→ {f.tier} tier{FEE[f.tier] ? `, ${money(FEE[f.tier])}` : ''} (confidence {f.confidence.toFixed(2)})</span>
            </p>
          ))}
          {model('image_analysis')}
        </>
      )
    case 'hearing': {
      const sides = [['rider', argumentOf(events, 'rider_advocate')], ['driver', argumentOf(events, 'driver_advocate')]] as const
      return (
        <>
          {sides.map(([role, a]) => a && (
            <p key={role}>
              <span className={`party ${role}`}><i />{role === 'rider' ? 'Rider' : 'Driver'}</span> “{firstSentence(a.text, 180)}” <span className="muted">self-rated {a.confidence.toFixed(2)}</span>
            </p>
          ))}
          {model('rider_advocate')}
        </>
      )
    }
    case 'judge':
      return dec ? (
        <>
          <p>
            <strong>{outcomeLabel(dec.outcome)}</strong>
            {dec.remedy.type !== 'no_action' ? ` · ${REMEDY[dec.remedy.type] ?? dec.remedy.type}${dec.remedy.amount ? ` ${money(dec.remedy.amount)}` : ''}` : ''} · confidence {dec.confidence.toFixed(2)}
          </p>
          <ul className="dp-list">
            {dec.reasoning.slice(0, 3).map((f, i) => (
              <li key={i}>{firstSentence(f.finding, 160)} {f.cites.slice(0, 2).map((c) => <Cite key={c} caseId={caseId} refId={c} />)}</li>
            ))}
          </ul>
          {model('judge')}
        </>
      ) : null
    case 'gates':
      return dec ? (
        <ul className="dp-list dp-checks">
          {gateChecks(dec).map(([ok, t, d]) => (
            <li key={t} className={ok ? 'pass' : 'flag'}><Icon name={ok ? 'check' : 'alert'} size={12} stroke={2.6} /> <strong>{t}</strong> <span className="muted">{d}</span></li>
          ))}
        </ul>
      ) : null
    case 'outcome':
      return state && OUTCOME_NOTE[state] ? <p>{OUTCOME_NOTE[state]}</p> : null
    default:
      return null
  }
}

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
  const [open, setOpen] = useState<StepKey | null>(null)

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
      <p className="small muted">{lede}{caseId && !failed ? ' Open a finished step to see what it did.' : ''}</p>
      <ol className="dp-steps">
        {steps.map((s) => {
          const cls = s.status === 'wait' ? 'idle' : s.status
          // A step that has happened opens to show what it did.
          const expandable = !!caseId && isLit(s.status)
          const isOpen = expandable && open === s.key
          const label = (
            <>
              {s.label}
              {s.status === 'now' && STEP_EXPLAIN[s.key] && <small>{STEP_EXPLAIN[s.key]}</small>}
              {s.status === 'wait' && <small>Starts when the other side replies.</small>}
            </>
          )
          return (
            <li key={s.key} className={`dp-row ${s.kind} ${cls}${isOpen ? ' open' : ''}`}>
              <span className="dp-ic">
                <Icon name={s.key === 'outcome' ? outcomeIcon(s.status) : STEP_ICON[s.key]} size={13} stroke={2.4} />
              </span>
              {expandable ? (
                <button className="dp-l dp-toggle" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : s.key)}>
                  {label}
                  <Icon name="right" size={13} stroke={2.2} />
                </button>
              ) : (
                <span className="dp-l">{label}</span>
              )}
              <span className="dp-t">
                {isLit(s.status) && s.kind !== 'person'
                  ? stepTime(events, usage, s.key)
                  : s.kind === 'rule' ? 'no AI' : s.kind === 'ai' ? 'AI' : ''}
              </span>
              {isOpen && caseId && (
                <div className="dp-more">
                  <StepDetail step={s.key} caseId={caseId} live={live} />
                </div>
              )}
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
