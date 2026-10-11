import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { PartyName } from '../components/Party'
import { Ruling } from '../components/Ruling'
import { StateBadge } from '../components/StateBadge'
import { StatusStepper } from '../components/StatusStepper'
import { api, streamUrl } from '../lib/api'
import { EvidenceProvider } from '../lib/evidence'
import { CATEGORY_LABEL, IN_PROGRESS, when } from '../lib/format'
import { savePersona } from '../lib/persona'
import { deriveStations, stationsFromState } from '../lib/pipeline'
import { useEventStream } from '../lib/useEventStream'
import type { CaseView, DecisionResponse, Role, TraceEvent } from '../types/api'

const RESPONSE_EXAMPLES: Record<Role, string> = {
  rider: "That's not what happened. I didn't cause this, and the trip record should show it.",
  driver: 'I followed the app and did what I was supposed to. The trip data will back me up.',
}

function nextStep(view: CaseView, iAmComplainer: boolean, otherName: string): { title: string; text: string } {
  switch (view.state) {
    case 'opened':
    case 'triage':
    case 'assembling':
      return {
        title: 'Checking the report',
        text: 'An agent is reading the report and assembling the trip record: GPS, route, fare, messages. Usually under a minute.',
      }
    case 'awaiting_response':
      return iAmComplainer
        ? {
            title: `Waiting for ${otherName}`,
            text: `${otherName} has been asked for their side. Nothing is decided until they respond or the response window closes.`,
          }
        : {
            title: 'Tell us your side',
            text: 'Nothing has been decided. Your response goes to the advocate arguing for you, alongside the trip record.',
          }
    case 'adjudicating':
      return {
        title: 'The hearing is under way',
        text: 'Two advocates are arguing each side from the identical trip record, then a Judge rules. About a minute.',
      }
    case 'escalated':
      return {
        title: 'A person is making the final call',
        text: 'The automated checks wanted a human to decide this one. A reviewer will look at the evidence and both sides; the decision will appear here.',
      }
    case 'safety_bypassed':
      return {
        title: 'With our safety team',
        text: 'Safety reports are never decided by an automated system. A safety specialist will contact you directly.',
      }
    case 'declined_insufficient_evidence':
      return {
        title: 'Declined, not denied',
        text: 'There wasn’t enough evidence to look into this, which is different from a ruling against you. You can report it again with the missing evidence.',
      }
    case 'decided':
      return {
        title: 'Decided',
        text: 'The decision below cites the evidence it relied on. Tap any reference to see it.',
      }
  }
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
    if (!lastEventId) return
    refresh()
    // The trace event can land a moment before the case row is updated.
    const t = setTimeout(refresh, 1500)
    return () => clearTimeout(t)
  }, [lastEventId, refresh])

  const state = view?.state
  const updated = view?.updated_at
  useEffect(() => {
    if (state === 'decided') api.decision(caseId).then(setDecision, () => setDecision(null))
  }, [state, updated, caseId])

  const stations = useMemo(
    () => (events.length ? deriveStations(events) : stationsFromState(state ?? 'opened')),
    [events, state],
  )
  const lastRule = [...events].reverse().find((e) => e.kind === 'rule_evaluation')

  if (error && !view) return <p className="error-text">{error}</p>
  if (!view)
    return (
      <div className="stack">
        <div className="skeleton" style={{ height: 40, width: '40%' }} />
        <div className="skeleton" style={{ height: 160 }} />
      </div>
    )

  const iAmComplainer = view.complainer_id === userId
  const otherName = iAmComplainer ? view.complainee_name : view.complainer_name
  const otherRole: Role = role === 'rider' ? 'driver' : 'rider'
  const otherId = iAmComplainer ? view.complainee_id : view.complainer_id
  const myTurn = !iAmComplainer && view.state === 'awaiting_response'
  const moving = IN_PROGRESS.includes(view.state)
  const next = nextStep(view, iAmComplainer, otherName)
  const complainerRole = view.complainer_role
  const complaineeRole: Role = complainerRole === 'rider' ? 'driver' : 'rider'

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
    <EvidenceProvider caseId={caseId} view="party">
      <div className="stack" style={{ gap: 20 }}>
        <div className="page-head" style={{ marginBottom: 0 }}>
          <div className="stack" style={{ gap: 6 }}>
            <Link to={`/${role}/${userId}`} className="small muted">
              ← Your disputes
            </Link>
            <span className="eyebrow">
              Dispute <span className="mono">{view.id}</span> · opened {when(view.created_at)}
            </span>
            <h1>{view.category ? CATEGORY_LABEL[view.category] : 'Dispute'}</h1>
            <p className="muted">
              {iAmComplainer ? (
                <>
                  You reported <PartyName role={complaineeRole} name={otherName} />
                </>
              ) : (
                <>
                  <PartyName role={complainerRole} name={otherName} /> reported you
                </>
              )}
            </p>
          </div>
          <div className="row">
            <StateBadge state={view.state} />
            <Link to={`/trace/${caseId}`} className="btn btn-sm">
              Watch the agents →
            </Link>
          </div>
        </div>

        <section className="panel panel-pad stack" style={{ gap: 16 }}>
          <StatusStepper stations={stations} />
          <div className="what-next">
            {moving ? <span className="spinner" style={{ marginTop: 3 }} /> : <span className="avatar ink" style={{ width: 22, height: 22, fontSize: '0.7rem' }}>i</span>}
            <div>
              <strong>{next.title}</strong>
              <p className="small muted">{next.text}</p>
              {view.state === 'declined_insufficient_evidence' && lastRule?.detail && (
                <p className="tiny faint mono" style={{ marginTop: 4 }}>
                  {lastRule.detail}
                </p>
              )}
            </div>
          </div>
          {view.state === 'declined_insufficient_evidence' && iAmComplainer && (
            <div>
              <Link to={`/${role}/${userId}/file/${view.trip_id}`} className="btn btn-primary btn-sm">
                Report again with evidence
              </Link>
            </div>
          )}
        </section>

        <div className="split">
          <div className="stack">
            {decision && (
              <Ruling
                decision={decision.decision}
                category={view.category}
                title={decision.decision.human_ratified ? 'Decision, reviewed by a person' : 'Decision'}
                gates={false}
              />
            )}

            <section className="panel hearing">
              <div className="panel-head">
                <h2>Both sides</h2>
                <span className="tiny faint">The Judge never sees this text, only the evidence and the advocates’ arguments.</span>
              </div>
              <div className="panel-body stack">
                <div className="stack" style={{ gap: 6 }}>
                  <PartyName role={complainerRole} name={iAmComplainer ? 'You' : view.complainer_name} />
                  <p className="quote" style={{ ['--party' as string]: `var(--${complainerRole})` }}>
                    {view.claim_text}
                  </p>
                </div>
                <div className="stack" style={{ gap: 6 }}>
                  <PartyName role={complaineeRole} name={iAmComplainer ? view.complainee_name : 'You'} />
                  {view.response ? (
                    <>
                      <p className="quote" style={{ ['--party' as string]: `var(--${complaineeRole})` }}>
                        {view.response.text}
                      </p>
                      <span className="tiny faint">responded {when(view.response.submitted_at)}</span>
                    </>
                  ) : myTurn ? (
                    <form className="stack" onSubmit={sendReply} style={{ gap: 10 }}>
                      <textarea value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Your side of what happened" required />
                      <div className="row">
                        <button className="btn-primary" disabled={sending || !reply.trim()}>
                          {sending ? (
                            <>
                              <span className="spinner" /> Sending…
                            </>
                          ) : (
                            'Send my side'
                          )}
                        </button>
                        <button type="button" className="btn-ghost btn-sm" onClick={() => setReply(RESPONSE_EXAMPLES[role])}>
                          Use example text
                        </button>
                      </div>
                      {error && <p className="error-text">{error}</p>}
                    </form>
                  ) : view.state === 'awaiting_response' ? (
                    <div className="stack" style={{ gap: 8 }}>
                      <p className="small muted">No response yet.</p>
                      <div className="row">
                        <button className="btn-sm" onClick={switchToOther}>
                          Demo: respond as {otherName}
                        </button>
                        <button className="btn-ghost btn-sm" onClick={adjudicateNow}>
                          Demo: skip waiting
                        </button>
                      </div>
                    </div>
                  ) : view.state === 'safety_bypassed' ? (
                    <p className="small faint">Not asked yet: a safety specialist handles this directly.</p>
                  ) : (
                    <p className="small faint">No response was given.</p>
                  )}
                </div>
              </div>
            </section>
          </div>

          <aside className="panel panel-pad stack" style={{ gap: 12 }}>
            <span className="eyebrow">How this is decided</span>
            <ul className="principles">
              <li>Both of you are heard. Each side gets its own advocate, arguing from the same trip record.</li>
              <li>The Judge rules on evidence and arguments. It never reads either person’s original words.</li>
              <li>Every finding cites a piece of evidence you can open.</li>
              <li>Refunds and fees come from Ryde’s published formula, computed in code, not chosen by the AI.</li>
              <li>Anything uncertain, high-value, repeated or safety-related goes to a person.</li>
            </ul>
          </aside>
        </div>
      </div>
    </EvidenceProvider>
  )
}
