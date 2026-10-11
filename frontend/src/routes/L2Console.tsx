import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { DecisionCard } from '../components/DecisionCard'
import { StateBadge } from '../components/StateBadge'
import { api, streamUrl } from '../lib/api'
import { CATEGORY_LABEL, OUTCOME_LABEL, REMEDY_LABEL, money, when } from '../lib/format'
import { loadReviewer, saveReviewer } from '../lib/persona'
import { useEventStream } from '../lib/useEventStream'
import type {
  DecisionObject,
  L2QueueItem,
  L2StreamEvent,
  Outcome,
  RemedyType,
} from '../types/api'

function ReviewForm({ item, agentDecision, onDone }: {
  item: L2QueueItem
  agentDecision: DecisionObject | null
  onDone: (d: DecisionObject) => void
}) {
  const [reviewer, setReviewer] = useState(loadReviewer())
  const [action, setAction] = useState<'ratify' | 'override'>(agentDecision ? 'ratify' : 'override')
  const [outcome, setOutcome] = useState<Outcome>((agentDecision?.outcome as Outcome) ?? 'claim_denied')
  const [remedyType, setRemedyType] = useState<RemedyType>(agentDecision?.remedy.type ?? 'no_action')
  const [amount, setAmount] = useState<string>(agentDecision?.remedy.amount?.toString() ?? '')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    saveReviewer(reviewer)
    try {
      const decision = await api.l2Review(item.id, {
        reviewer,
        action,
        note: note.trim(),
        ...(action === 'override'
          ? {
              outcome,
              remedy: {
                type: remedyType,
                amount: remedyType === 'no_action' || amount === '' ? null : Number(amount),
              },
            }
          : {}),
      })
      onDone(decision)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card stack" onSubmit={submit}>
      <h3>Your review</h3>
      <div className="segmented">
        <button
          type="button"
          className={action === 'ratify' ? 'on' : ''}
          onClick={() => setAction('ratify')}
          disabled={!agentDecision}
          title={agentDecision ? '' : 'No agent decision exists. Safety cases are decided by a human only.'}
        >
          Ratify
        </button>
        <button
          type="button"
          className={action === 'override' ? 'on' : ''}
          onClick={() => setAction('override')}
        >
          Override
        </button>
      </div>
      {action === 'override' && (
        <div className="grid-2">
          <label>
            Outcome
            <select value={outcome} onChange={(e) => setOutcome(e.target.value as Outcome)}>
              {(Object.keys(OUTCOME_LABEL) as Outcome[]).map((o) => (
                <option key={o} value={o}>
                  {OUTCOME_LABEL[o]}
                </option>
              ))}
            </select>
          </label>
          <label>
            Remedy
            <select value={remedyType} onChange={(e) => setRemedyType(e.target.value as RemedyType)}>
              {(Object.keys(REMEDY_LABEL) as RemedyType[]).map((r) => (
                <option key={r} value={r}>
                  {REMEDY_LABEL[r]}
                </option>
              ))}
            </select>
          </label>
          {remedyType !== 'no_action' && (
            <label>
              Amount ($)
              <input
                type="number"
                min="0"
                step="0.01"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                required
              />
            </label>
          )}
        </div>
      )}
      <label>
        Note (recorded on the decision)
        <textarea value={note} onChange={(e) => setNote(e.target.value)} required style={{ minHeight: 70 }} />
      </label>
      <label>
        Reviewer
        <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} required />
      </label>
      {error && <p className="error-text">{error}</p>}
      <div>
        <button className="primary" disabled={busy || !note.trim()}>
          {busy ? <span className="spinner" /> : action === 'ratify' ? 'Ratify decision' : 'Submit override'}
        </button>
      </div>
      <p className="small muted" style={{ margin: 0 }}>
        Overrides still go through the compliance check: remedies that break policy caps are
        rejected, even from a human.
      </p>
    </form>
  )
}

export function L2Console() {
  const { caseId } = useParams()
  const navigate = useNavigate()
  const [queue, setQueue] = useState<L2QueueItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [agentDecision, setAgentDecision] = useState<DecisionObject | null>(null)
  const [finalDecision, setFinalDecision] = useState<DecisionObject | null>(null)
  const { events } = useEventStream<L2StreamEvent>(streamUrl.l2())

  const load = useCallback(() => {
    api.l2Queue().then(setQueue, (e: Error) => setError(e.message))
  }, [])
  const lastEvent = events[events.length - 1]?.id
  useEffect(load, [load, lastEvent])

  const selected = queue?.find((q) => q.id === caseId) ?? null

  useEffect(() => setFinalDecision(null), [caseId])

  const selectedState = selected?.state
  useEffect(() => {
    setAgentDecision(null)
    if (caseId && selectedState === 'escalated') {
      api.decision(caseId).then((d) => setAgentDecision(d.decision), () => setAgentDecision(null))
    }
  }, [caseId, selectedState])

  return (
    <>
      <div className="page-head">
        <div>
          <h1>L2 review console</h1>
          <p>
            Cases a person has to decide: everything the escalation gate sent up, and every safety
            incident. New arrivals appear live.
          </p>
        </div>
      </div>
      {error && <p className="error-text">{error}</p>}

      <div className="grid-main" style={{ gridTemplateColumns: 'minmax(0, 340px) minmax(0, 1fr)' }}>
        <section className="card" style={{ padding: 8 }}>
          <h3 style={{ padding: '6px 8px' }}>
            Queue {queue && <span className="muted">({queue.length})</span>}
          </h3>
          {queue?.length === 0 && <div className="empty">Nothing waiting.</div>}
          <div className="list">
            {queue?.map((q) => (
              <Link
                key={q.id}
                to={`/l2/${q.id}`}
                className={`list-item${q.id === caseId ? ' selected' : ''}`}
                style={{ padding: 8 }}
              >
                <div className="grow">
                  <div className="title small">
                    {q.id} · {q.category ? CATEGORY_LABEL[q.category] : '—'}
                  </div>
                  <div className="small faint">
                    {q.complainer_name} vs {q.complainee_name} · {when(q.updated_at)}
                  </div>
                </div>
                <StateBadge state={q.state} />
              </Link>
            ))}
          </div>
        </section>

        {finalDecision ? (
          <section className="stack">
            <div className="callout tone-good">
              <strong>Done.</strong> {finalDecision.case_id} is now final.{' '}
              <Link to={`/trace/${finalDecision.case_id}`}>View its trace</Link>
            </div>
            <DecisionCard decision={finalDecision} title="Final decision" />
            <div>
              <button onClick={() => navigate('/l2')}>Back to the queue</button>
            </div>
          </section>
        ) : selected ? (
          <section className="stack">
            <div className="card">
              <div className="card-head">
                <h2>
                  {selected.id} · {selected.category ? CATEGORY_LABEL[selected.category] : ''}
                </h2>
                <Link to={`/trace/${selected.id}`} className="button small">
                  Full trace →
                </Link>
              </div>
              <dl className="kv">
                <dt>Filed by</dt>
                <dd>
                  {selected.complainer_name} ({selected.complainer_role})
                </dd>
                <dt>Against</dt>
                <dd>{selected.complainee_name}</dd>
                <dt>Opened</dt>
                <dd>{when(selected.created_at)}</dd>
                {selected.remedy && (
                  <>
                    <dt>Agent remedy</dt>
                    <dd>
                      {REMEDY_LABEL[selected.remedy.type]} {selected.remedy.amount ? money(selected.remedy.amount) : ''}
                    </dd>
                  </>
                )}
              </dl>
              <p className="quote small" style={{ marginTop: 10 }}>
                {selected.claim_text}
              </p>
              {selected.state === 'safety_bypassed' && (
                <div className="callout tone-bad">
                  Safety incident: no agent saw this case. Decide it directly.
                </div>
              )}
            </div>
            {agentDecision && <DecisionCard decision={agentDecision} title="Agent recommendation" />}
            <ReviewForm
              key={selected.id + String(Boolean(agentDecision))}
              item={selected}
              agentDecision={agentDecision}
              onDone={(d) => {
                setFinalDecision(d)
                load()
              }}
            />
          </section>
        ) : (
          <div className="empty">Pick a case from the queue.</div>
        )}
      </div>
    </>
  )
}
