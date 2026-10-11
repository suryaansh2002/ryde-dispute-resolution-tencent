import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { PartyName } from '../components/Party'
import { Ruling } from '../components/Ruling'
import { api, streamUrl } from '../lib/api'
import { EvidenceProvider } from '../lib/evidence'
import { CATEGORY_LABEL, OUTCOME_LABEL, REMEDY_LABEL, ago, money, toneClass, when, whyLabels } from '../lib/format'
import { loadReviewer, saveReviewer } from '../lib/persona'
import { useEventStream } from '../lib/useEventStream'
import type { DecisionObject, L2QueueItem, L2StreamEvent, Outcome, RemedyType, Role } from '../types/api'

const OVERRIDE_REASONS = [
  'Evidence misread',
  'Policy misapplied',
  'Remedy amount wrong',
  'New information from a party',
  'Safety: action taken',
  'Other',
]

function ReviewForm({
  item,
  agentDecision,
  action,
  setAction,
  noteRef,
  onDone,
}: {
  item: L2QueueItem
  agentDecision: DecisionObject | null
  action: 'ratify' | 'override'
  setAction: (a: 'ratify' | 'override') => void
  noteRef: React.RefObject<HTMLTextAreaElement | null>
  onDone: (d: DecisionObject) => void
}) {
  const [reviewer, setReviewer] = useState(loadReviewer())
  const [reason, setReason] = useState<string | null>(item.is_safety ? 'Safety: action taken' : null)
  const [outcome, setOutcome] = useState<Outcome>((agentDecision?.outcome as Outcome) ?? 'claim_denied')
  const [remedyType, setRemedyType] = useState<RemedyType>(agentDecision?.remedy.type ?? 'no_action')
  const [amount, setAmount] = useState<string>(agentDecision?.remedy.amount?.toString() ?? '')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const ready = action === 'ratify' ? Boolean(agentDecision) : Boolean(reason && note.trim())

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    saveReviewer(reviewer)
    const text =
      action === 'ratify'
        ? note.trim() || 'Ratified as recommended.'
        : `[${reason}] ${note.trim()}`
    try {
      const decision = await api.l2Review(item.id, {
        reviewer,
        action,
        note: text,
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
    <form className="panel panel-pad stack" onSubmit={submit}>
      <div className="row between">
        <h3>Your decision</h3>
        <div className="segmented">
          <button
            type="button"
            className={action === 'ratify' ? 'on' : ''}
            onClick={() => setAction('ratify')}
            disabled={!agentDecision}
            title={agentDecision ? 'Shortcut: A' : 'No agent recommendation exists. Safety reports are decided by a person only.'}
          >
            Ratify <kbd>A</kbd>
          </button>
          <button type="button" className={action === 'override' ? 'on' : ''} onClick={() => setAction('override')} title="Shortcut: O">
            {agentDecision ? 'Override' : 'Decide'} <kbd>O</kbd>
          </button>
        </div>
      </div>

      {action === 'override' && (
        <>
          <div className="stack" style={{ gap: 6 }}>
            <span className="eyebrow">Reason</span>
            <div className="reason-grid">
              {OVERRIDE_REASONS.map((r) => (
                <button key={r} type="button" className={reason === r ? 'on' : ''} onClick={() => setReason(r)}>
                  {r}
                </button>
              ))}
            </div>
          </div>
          <div className="grid-3">
            <label className="field">
              Outcome
              <select value={outcome} onChange={(e) => setOutcome(e.target.value as Outcome)}>
                {(Object.keys(OUTCOME_LABEL) as Outcome[]).map((o) => (
                  <option key={o} value={o}>
                    {OUTCOME_LABEL[o]}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
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
              <label className="field">
                Amount ($)
                <input type="number" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} required />
              </label>
            )}
          </div>
        </>
      )}
      <label className="field">
        {action === 'ratify' ? 'Note (optional)' : 'Note, recorded on the decision'}
        <textarea
          ref={noteRef}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          required={action === 'override'}
          style={{ minHeight: 70 }}
          placeholder={action === 'ratify' ? 'Ratified as recommended.' : agentDecision ? 'What the agents got wrong, and what you decided.' : 'What you found, and what you decided.'}
        />
      </label>
      <div className="row between">
        <label className="field" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <span className="tiny muted">Reviewer</span>
          <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} required style={{ width: 170, padding: '5px 8px' }} />
        </label>
        <button className="btn-primary" disabled={busy || !ready}>
          {busy ? <span className="spinner" /> : action === 'ratify' ? 'Ratify and finalise' : agentDecision ? 'Override and finalise' : 'Record decision'}
        </button>
      </div>
      {error && <p className="error-text">{error}</p>}
      <p className="tiny faint">
        Overrides still pass the compliance check: a remedy that breaks the policy caps is rejected, even from a person.
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
  const [action, setAction] = useState<'ratify' | 'override'>('ratify')
  const noteRef = useRef<HTMLTextAreaElement | null>(null)
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
    setAction(selectedState === 'escalated' ? 'ratify' : 'override')
    if (caseId && selectedState === 'escalated') {
      api.decision(caseId).then((d) => setAgentDecision(d.decision), () => setAgentDecision(null))
    }
  }, [caseId, selectedState])

  // Keyboard: J/K move through the queue, A ratify, O override. Not while typing.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (t.closest('input, textarea, select') || e.metaKey || e.ctrlKey || e.altKey) return
      if (!queue?.length) return
      const i = queue.findIndex((q) => q.id === caseId)
      if (e.key === 'j' || e.key === 'k') {
        const next = e.key === 'j' ? Math.min(queue.length - 1, i + 1) : Math.max(0, i - 1)
        navigate(`/l2/${queue[i < 0 ? 0 : next].id}`)
      } else if (e.key === 'a' && agentDecision) {
        setAction('ratify')
        setTimeout(() => noteRef.current?.focus(), 0)
        e.preventDefault()
      } else if (e.key === 'o' && selected) {
        setAction('override')
        setTimeout(() => noteRef.current?.focus(), 0)
        e.preventDefault()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [queue, caseId, navigate, agentDecision, selected])

  const complaineeRole = (r: Role): Role => (r === 'rider' ? 'driver' : 'rider')

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="page-head" style={{ marginBottom: 0 }}>
        <div className="stack" style={{ gap: 6 }}>
          <h1>Human review</h1>
          <p className="lead">
            Cases a person decides: everything the escalation gate flagged, and every safety report. New arrivals appear
            live.
          </p>
        </div>
        <span className="tiny faint">
          <kbd>J</kbd> <kbd>K</kbd> move · <kbd>A</kbd> ratify · <kbd>O</kbd> override
        </span>
      </div>
      {error && <p className="error-text">{error}</p>}

      <div className="split-l2">
        <section className="panel sticky">
          <div className="panel-head">
            <h3>Queue</h3>
            <span className="badge">{queue?.length ?? '…'} waiting</span>
          </div>
          {queue?.length === 0 && (
            <div className="panel-body">
              <div className="empty">Nothing waiting. Every case so far cleared the gates or was reviewed.</div>
            </div>
          )}
          {queue && queue.length > 0 && (
            <div className="table-wrap" style={{ maxHeight: '72vh', overflowY: 'auto' }}>
              <table className="queue">
                <thead>
                  <tr>
                    <th>Case</th>
                    <th>Why a person</th>
                    <th className="num">Conf.</th>
                    <th className="num">At stake</th>
                    <th className="num">Waiting</th>
                  </tr>
                </thead>
                <tbody>
                  {queue.map((q) => (
                    <tr
                      key={q.id}
                      className={`${q.id === caseId ? 'selected' : ''} ${q.is_safety ? 'safety' : ''}`}
                      onClick={() => navigate(`/l2/${q.id}`)}
                    >
                      <td>
                        <Link to={`/l2/${q.id}`} style={{ textDecoration: 'none', fontWeight: 600 }} onClick={(e) => e.stopPropagation()}>
                          {q.category ? CATEGORY_LABEL[q.category] : '—'}
                        </Link>
                        <div className="tiny faint mono">{q.id}</div>
                      </td>
                      <td>
                        <div className="chips">
                          {whyLabels(q).map((w) => (
                            <span key={w.label} className={`badge ${toneClass(w.tone)}`}>
                              {w.label}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="num mono">{q.confidence == null ? '—' : q.confidence.toFixed(2)}</td>
                      <td className="num mono">{q.remedy?.amount ? money(q.remedy.amount) : '—'}</td>
                      <td className="num tiny muted">{ago(q.updated_at).replace(' ago', '')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {finalDecision ? (
          <EvidenceProvider caseId={finalDecision.case_id} view="operator">
            <section className="stack">
              <div className="banner tone-good" style={{ margin: 0 }}>
                <span>
                  <strong>Done.</strong> <span className="mono">{finalDecision.case_id}</span> is final.{' '}
                  <Link to={`/trace/${finalDecision.case_id}`}>See its trace</Link>
                </span>
              </div>
              <Ruling decision={finalDecision} category={null} title="Final decision" gates={false} />
              <div className="row">
                <button
                  className="btn-primary"
                  onClick={() => {
                    const next = queue?.find((q) => q.id !== finalDecision.case_id)
                    navigate(next ? `/l2/${next.id}` : '/l2')
                  }}
                >
                  Next case <kbd>J</kbd>
                </button>
              </div>
            </section>
          </EvidenceProvider>
        ) : selected ? (
          <EvidenceProvider key={selected.id} caseId={selected.id} view="operator">
            <section className="stack">
              <div className="panel">
                <div className="panel-head" style={{ alignItems: 'flex-start' }}>
                  <div className="stack" style={{ gap: 4 }}>
                    <span className="eyebrow">
                      Case <span className="mono">{selected.id}</span> · opened {when(selected.created_at)}
                    </span>
                    <h2>{selected.category ? CATEGORY_LABEL[selected.category] : 'Case'}</h2>
                    <div className="small row" style={{ gap: 6 }}>
                      <PartyName role={selected.complainer_role} name={selected.complainer_name} />
                      <span className="faint">reported</span>
                      <PartyName role={complaineeRole(selected.complainer_role)} name={selected.complainee_name} />
                    </div>
                  </div>
                  <Link to={`/trace/${selected.id}`} className="btn btn-sm">
                    Full trace →
                  </Link>
                </div>
                <div className="panel-body stack">
                  <div className="chips">
                    {whyLabels(selected).map((w) => (
                      <span key={w.label} className={`badge ${toneClass(w.tone)}`}>
                        {w.label}
                      </span>
                    ))}
                  </div>
                  <p className="quote small" style={{ ['--party' as string]: `var(--${selected.complainer_role})` }}>
                    {selected.claim_text}
                  </p>
                  {selected.state === 'safety_bypassed' && (
                    <div className="banner tone-bad" style={{ margin: 0 }}>
                      <span>
                        <strong>Safety report.</strong> No agent has seen this case. Contact the parties and decide it
                        directly.
                      </span>
                    </div>
                  )}
                </div>
              </div>
              {agentDecision && (
                <Ruling decision={agentDecision} category={selected.category} title="Agents’ recommendation" />
              )}
              <ReviewForm
                key={selected.id + String(Boolean(agentDecision))}
                item={selected}
                agentDecision={agentDecision}
                action={action}
                setAction={setAction}
                noteRef={noteRef}
                onDone={(d) => {
                  setFinalDecision(d)
                  load()
                }}
              />
            </section>
          </EvidenceProvider>
        ) : (
          <div className="empty">
            Pick a case from the queue, or press <kbd>J</kbd>.
          </div>
        )}
      </div>
    </div>
  )
}
