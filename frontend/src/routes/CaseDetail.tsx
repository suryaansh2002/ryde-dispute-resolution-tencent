import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { DecisionDocument } from '../components/DecisionDocument'
import { StateBadge } from '../components/StateBadge'
import { api, streamUrl } from '../lib/api'
import { CATEGORY_LABEL, IN_PROGRESS, STATE_LABEL, when } from '../lib/format'
import { savePersona } from '../lib/persona'
import { useEventStream } from '../lib/useEventStream'
import type { CaseState, CaseView, DecisionResponse, Role, TraceEvent } from '../types/api'

const DECISION_STATES: CaseState[] = ['decided', 'escalated']

const RESPONSE_EXAMPLES: Record<Role, string> = {
  rider: "That's not what happened. I didn't cause this, and the trip record should show it.",
  driver: 'I followed the app and did what I was supposed to. The trip data will back me up.',
}

export function CaseDetail() {
  const { role, userId, caseId } = useParams() as { role: Role; userId: string; caseId: string }
  const navigate = useNavigate()
  const [view, setView] = useState<CaseView | null>(null)
  const [decision, setDecision] = useState<DecisionResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reply, setReply] = useState('')
  const [sending, setSending] = useState(false)
  const { events } = useEventStream<TraceEvent>(streamUrl.case(caseId))

  const refresh = useCallback(() => {
    api.caseView(caseId).then(setView, (e: Error) => setError(e.message))
  }, [caseId])
  useEffect(refresh, [refresh])

  // Every new trace event can change the case: re-read it.
  const lastEventId = events[events.length - 1]?.id
  useEffect(() => {
    if (lastEventId) refresh()
  }, [lastEventId, refresh])

  useEffect(() => {
    if (view && DECISION_STATES.includes(view.state)) {
      api.decision(caseId).then(setDecision, () => setDecision(null))
    }
  }, [view?.state, view?.updated_at, caseId, view])

  const steps = useMemo(
    () => events.filter((e) => e.kind === 'state_transition' || e.kind === 'error'),
    [events],
  )
  const lastRule = [...events].reverse().find((e) => e.kind === 'rule_evaluation')

  if (error) return <p className="error-text">{error}</p>
  if (!view)
    return (
      <p className="muted">
        <span className="spinner" /> Loading case…
      </p>
    )

  const iAmComplainer = view.complainer_id === userId
  const otherName = iAmComplainer ? view.complainee_name : view.complainer_name
  const otherRole: Role = role === 'rider' ? 'driver' : 'rider'
  const otherId = iAmComplainer ? view.complainee_id : view.complainer_id
  const myTurn = !iAmComplainer && view.state === 'awaiting_response'
  const moving = IN_PROGRESS.includes(view.state)

  const switchToOther = () => {
    savePersona({ id: otherId, role: otherRole, name: otherName })
    navigate(`/${otherRole}/${otherId}/case/${caseId}`)
  }

  const sendReply = async (e: FormEvent) => {
    e.preventDefault()
    setSending(true)
    setError(null)
    try {
      await api.respond(caseId, userId, reply.trim())
      setReply('')
      refresh()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSending(false)
    }
  }

  const adjudicateNow = () => {
    api.adjudicateNow(caseId).catch((err: Error) => setError(err.message))
    setTimeout(refresh, 1500)
  }

  return (
    <>
      <div className="page-head">
        <div>
          <Link to={`/${role}/${userId}`} className="small">
            ← Back to your panel
          </Link>
          <h1 style={{ marginTop: 6 }}>
            {view.category ? CATEGORY_LABEL[view.category] : 'Dispute'}{' '}
            <span className="muted mono" style={{ fontSize: '0.9rem' }}>
              {view.id}
            </span>
          </h1>
          <p>
            {iAmComplainer ? `You filed this against ${otherName}` : `${otherName} filed this against you`}{' '}
            · opened {when(view.created_at)}
          </p>
        </div>
        <div className="row">
          <StateBadge state={view.state} />
          <Link to={`/trace/${caseId}`} className="button small">
            Watch the agents →
          </Link>
        </div>
      </div>

      <div className="grid-main">
        <div className="stack">
          {decision && (
            <section className="card">
              <DecisionDocument markdown={decision.document} />
            </section>
          )}

          {view.state === 'safety_bypassed' && (
            <div className="callout tone-bad">
              <strong>Sent straight to a human reviewer.</strong> The claim describes a possible
              safety issue, and those are never decided by an automated system. No agent argued
              this case.
            </div>
          )}
          {view.state === 'declined_insufficient_evidence' && (
            <div className="callout tone-neutral">
              <strong>Declined: not enough evidence to proceed.</strong> This isn't a ruling against
              you. The claim can be refiled with better evidence.
              {lastRule?.detail && <div className="small mono" style={{ marginTop: 6 }}>{lastRule.detail}</div>}
            </div>
          )}

          <section className="card">
            <h3>{iAmComplainer ? 'Your claim' : `${view.complainer_name}'s claim against you`}</h3>
            <p className="quote">{view.claim_text}</p>
          </section>

          <section className="card">
            <h3>{iAmComplainer ? `${view.complainee_name}'s response` : 'Your response'}</h3>
            {view.response ? (
              <>
                <p className="quote">{view.response.text}</p>
                <p className="small faint">submitted {when(view.response.submitted_at)}</p>
              </>
            ) : myTurn ? (
              <form className="stack" onSubmit={sendReply}>
                <textarea
                  value={reply}
                  onChange={(e) => setReply(e.target.value)}
                  placeholder="Your side of what happened"
                  required
                />
                <div className="row">
                  <button className="primary" disabled={sending || !reply.trim()}>
                    {sending ? (
                      <>
                        <span className="spinner" /> Sending…
                      </>
                    ) : (
                      'Send response'
                    )}
                  </button>
                  <button type="button" className="small" onClick={() => setReply(RESPONSE_EXAMPLES[role])}>
                    Use example text
                  </button>
                </div>
                <p className="small muted">
                  Sending starts the hearing: an advocate for each side, then the Judge. It takes
                  about a minute; you can watch it live.
                </p>
              </form>
            ) : view.state === 'awaiting_response' ? (
              <div className="stack">
                <p className="muted">Waiting for {otherName} to respond.</p>
                <div className="row">
                  <button className="small" onClick={switchToOther}>
                    Demo: switch to {otherName} to respond
                  </button>
                  <button className="small" onClick={adjudicateNow}>
                    Skip waiting: decide now
                  </button>
                </div>
              </div>
            ) : (
              <p className="muted">No response.</p>
            )}
          </section>
        </div>

        <aside className="card">
          <div className="card-head">
            <h3>Progress</h3>
            {moving && <span className="spinner" />}
          </div>
          {steps.length === 0 ? (
            <p className="muted small">
              <span className="spinner" /> Connecting…
            </p>
          ) : (
            <div className="timeline">
              {steps.map((e) => (
                <div key={e.id} className="tl-item">
                  <span className="tl-time">
                    {new Date(e.t).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' })}
                  </span>
                  <div className={`tl-line${e.kind === 'error' ? ' error-text' : ''}`}>
                    {e.kind === 'error'
                      ? e.detail
                      : e.detail?.includes('->')
                        ? STATE_LABEL[e.detail.split('->')[1].trim() as CaseState] ?? e.detail
                        : e.detail}
                  </div>
                </div>
              ))}
            </div>
          )}
        </aside>
      </div>
    </>
  )
}
