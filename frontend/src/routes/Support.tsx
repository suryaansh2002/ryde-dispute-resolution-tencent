import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import type { DecisionObject, EvidenceIndex, L2QueueItem, L2StreamEvent, Outcome, Remedy } from '../types/api'
import { api, streamUrl } from '../lib/api'
import { ago, CAT, CAT_FULL, clock, day, minutesBetween, money, outcomeLabel } from '../lib/format'
import { argumentOf } from '../lib/hearing'
import { useEvidence, useLiveCase } from '../lib/live'
import { invalidate, useApi } from '../lib/useApi'
import { useEventStream } from '../lib/useEventStream'
import { Chat, Cite, photoUrl } from '../components/evidence'
import { Icon } from '../components/Icon'
import { TripMap, geoFromEvidence } from '../components/TripMap'
import { ArgText, ErrorNote, Loading, Verdict } from '../components/ui'

/* The support console: cases a person decides. Evidence first, the AI's recommendation
   only on request, so it doesn't anchor the reviewer. */

const REVIEWER = 'Support reviewer'
const OVERRIDE_REASONS = ['Evidence misread', 'Policy misapplied', 'Amount wrong', 'New information', 'Safety action taken', 'Other']

function whyText(q: L2QueueItem) {
  if (q.is_safety) return 'Safety report. No AI has decided anything.'
  const out: string[] = []
  const r = q.escalation?.reasons ?? []
  if (r.some((x) => x.startsWith('bucket: high_value'))) out.push('Fee of $120 or more')
  if (r.some((x) => x.startsWith('bucket: repeat_filer'))) out.push('3+ disputes in 30 days')
  if (q.escalation?.confidence_escalate) out.push('Low confidence')
  if (r.some((x) => x.startsWith('Judge requested'))) out.push('The Judge asked for a person')
  if (q.escalation?.compliance_veto) out.push('A rule check failed')
  return out.join(' · ') || 'Flagged by the checks'
}

function whyChips(q: L2QueueItem): [string, string][] {
  if (q.is_safety) return [['bad', 'Safety']]
  const out: [string, string][] = []
  for (const r of q.escalation?.reasons ?? []) {
    if (r.startsWith('bucket: repeat_filer')) out.push(['warn', 'Repeat filer'])
    if (r.startsWith('bucket: high_value')) out.push(['warn', 'High-value fee'])
    if (r.startsWith('Judge requested')) out.push(['neutral', 'Judge asked'])
  }
  if (q.escalation?.confidence_escalate) out.push(['warn', 'Low confidence'])
  if (q.escalation?.compliance_veto) out.push(['bad', 'Rule check failed'])
  return out
}

const CAT_ICON = { route_deviation: 'route', no_show_charge: 'pin', property_damage: 'camera', safety_incident: 'shield' } as const

export function Support() {
  const { caseId } = useParams()
  const navigate = useNavigate()
  const { data: queue, error, reload } = useApi('l2:queue', api.l2Queue, true)
  const [toast, setToast] = useState<string | null>(null)
  const [done, setDone] = useState<string[]>([])

  // New arrivals: any case entering the queue (or leaving it) refreshes the list.
  const { events } = useEventStream<L2StreamEvent>(streamUrl.l2())
  useEffect(() => {
    if (events.length) reload()
  }, [events.length, reload])

  const pending = (queue ?? []).filter((q) => !done.includes(q.id))
  // Safety reports newest first; flagged cases keep the backend's oldest-first order.
  const safety = pending
    .filter((q) => q.is_safety)
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))
  const flagged = pending.filter((q) => !q.is_safety)
  const items = [...safety, ...flagged]
  const sel = items.find((q) => q.id === caseId) ?? items[0]

  const move = (dir: number) => {
    const i = items.findIndex((q) => q.id === sel?.id)
    const n = items[Math.min(items.length - 1, Math.max(0, i + dir))]
    if (n) navigate(`/support/${n.id}`, { replace: true })
  }
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest('input, textarea, select')) return
      if (e.key === 'j' || e.key === 'ArrowDown') { e.preventDefault(); move(1) }
      if (e.key === 'k' || e.key === 'ArrowUp') { e.preventDefault(); move(-1) }
    }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  })

  const finish = (id: string, msg: string) => {
    const i = items.findIndex((q) => q.id === id)
    const rest = items.filter((q) => q.id !== id)
    setDone((d) => [...d, id])
    invalidate(`outcome:${id}`)
    const next = rest[Math.min(i, rest.length - 1)]
    navigate(next ? `/support/${next.id}` : '/support', { replace: true })
    setToast(msg)
    setTimeout(() => setToast(null), 2600)
  }

  const groups: [string, L2QueueItem[]][] = [
    ['Safety reports', safety],
    ['Flagged by the checks', flagged],
  ]

  return (
    <div className="page">
      <div className="page-title">
        <div>
          <h1>Support console</h1>
          <p>Cases a person decides: every safety report, and everything the plain-code checks flagged. Safety is always first.</p>
        </div>
        <span className="small muted"><kbd>J</kbd> <kbd>K</kbd> move · <kbd>A</kbd> approve · <kbd>C</kbd> change</span>
      </div>
      {error && <div style={{ marginBottom: 20 }}><ErrorNote error={error} retry={reload} /></div>}
      <div className="console">
        <section className="panel" aria-label="Queue">
          <div className="panel-head"><h2>Waiting for review</h2><span className="small muted num">{queue ? `${items.length} cases` : ''}</span></div>
          {!queue && !error && <Loading />}
          {queue && items.length === 0 && (
            <div style={{ padding: '8px 20px 24px' }}><p className="muted">The queue is clear. New cases appear here the moment a check flags them.</p></div>
          )}
          {groups.map(([g, list]) => list.length > 0 && (
            <div key={g} className="inbox-group">
              <h3 className="inbox-h">{g}<span>{list.length}</span></h3>
              {list.map((q) => (
                <button key={q.id} className="inbox-row" aria-current={q.id === sel?.id} onClick={() => navigate(`/support/${q.id}`, { replace: true })}>
                  <span className={`inbox-ic ${q.is_safety ? 'bad' : ''}`}><Icon name={q.is_safety ? 'shield' : CAT_ICON[q.category ?? 'route_deviation']} size={16} /></span>
                  <span className="inbox-main">
                    <span className="inbox-t">{q.complainer_name}<span className="muted"> · {q.category ? CAT[q.category] : 'Report'}</span></span>
                    <span className="inbox-why">{whyText(q)}</span>
                  </span>
                  <span className="inbox-meta">
                    <span className="num">{q.remedy?.amount ? money(q.remedy.amount) : ''}</span>
                    <span>{ago(q.updated_at)}</span>
                  </span>
                </button>
              ))}
            </div>
          ))}
        </section>
        {sel ? (
          <ReviewCase key={sel.id} item={sel} onDone={finish} />
        ) : queue ? (
          <section className="panel" style={{ padding: 40 }}>
            <h2 style={{ fontSize: 22 }}>All caught up</h2>
            <p className="muted" style={{ marginTop: 6 }}>Every flagged case has a decision from a person.</p>
          </section>
        ) : null}
      </div>
      {toast && <div className="toast" role="status"><Icon name="check" size={16} stroke={2.4} />{toast}</div>}
    </div>
  )
}

type Mode = null | 'change'

function ReviewCase({ item, onDone }: { item: L2QueueItem; onDone: (id: string, msg: string) => void }) {
  const id = item.id
  const live = useLiveCase(id)
  const [prepared, setPrepared] = useState(0)
  const { data: ev } = useEvidence(item.is_safety && !prepared && !live.view?.has_case_file ? null : id, 'operator', String(prepared))
  const dec = live.decision?.decision
  const [showAI, setShowAI] = useState(false)
  const [mode, setMode] = useState<Mode>(null)
  const [reason, setReason] = useState<string | null>(item.is_safety ? 'Safety action taken' : null)
  const [note, setNote] = useState('')
  const [revealed, setRevealed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<Error | null>(null)
  const [override, setOverride] = useState<{ outcome: Outcome; remedy: Remedy } | null>(null)

  const photo = ev ? Object.entries(ev).find(([, e]) => e.kind === 'photo') : undefined
  const riderArg = argumentOf(live.events, 'rider_advocate')
  const driverArg = argumentOf(live.events, 'driver_advocate')
  const otherRole = item.complainer_role === 'rider' ? 'driver' : 'rider'

  const approve = async () => {
    setBusy(true)
    setErr(null)
    try {
      await api.l2Review(id, { reviewer: REVIEWER, action: 'ratify', note: 'Approved the recommendation as it stands.' })
      onDone(id, `${id} approved. The decision is final.`)
    } catch (e) {
      setErr(e as Error)
    } finally {
      setBusy(false)
    }
  }
  const save = async () => {
    if (!reason || !override) return
    setBusy(true)
    setErr(null)
    try {
      await api.l2Review(id, { reviewer: REVIEWER, action: 'override', note: `${reason}: ${note.trim()}`, ...override })
      onDone(id, `${id} recorded: ${reason}.`)
    } catch (e) {
      setErr(e as Error)
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest('input, textarea, select')) return
      if (e.key === 'a' && dec && !item.is_safety && mode !== 'change') { setShowAI(true); approve() }
      if (e.key === 'c') setMode('change')
    }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  })

  return (
    <section className="panel" aria-label={`Case ${id}`} style={{ overflow: 'hidden' }}>
      <div style={{ padding: '22px 24px 18px', display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <p className="small muted"><span className="mono">{id}</span> · reported {day(item.created_at)} · waiting {ago(item.updated_at)}</p>
          <h2 style={{ fontSize: 26, letterSpacing: '-0.02em' }}>{item.category ? CAT_FULL[item.category] : 'Report'}</h2>
          <p className="small">
            <span className={`party ${item.complainer_role}`}><i />{item.complainer_name}</span> <span className="muted">reported</span>{' '}
            <span className={`party ${otherRole}`}><i />{item.complainee_name}</span>
          </p>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          {whyChips(item).map(([t, l]) => <span key={l} className={`pill ${t}`}>{l}</span>)}
          <Link className="btn btn-secondary btn-sm" to={`/trace/${id}`}>Full trace</Link>
        </div>
      </div>
      <div className="section"><h3>What they said</h3><p style={{ color: 'var(--ink-2)', maxWidth: '70ch' }}>“{item.claim_text}”</p></div>

      {item.is_safety ? (
        <div className="section">
          <h3>Evidence</h3>
          <SafetyPrep item={item} ev={ev} prepared={!!ev && Object.keys(ev).length > 0} onPrepared={() => setPrepared((n) => n + 1)} />
        </div>
      ) : (
        <>
          <div className="section">
            <h3>Evidence</h3>
            {!ev && <Loading label="Loading the case file…" />}
            {photo && (
              <div className={`photo${revealed ? '' : ' blur'}`} style={{ maxWidth: 440 }}>
                <img src={photoUrl(photo[1])} alt="Photo evidence" />
                {!revealed && (
                  <button className="reveal" onClick={() => setRevealed(true)}>
                    <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}><Icon name="eye" size={18} />Show photo</span>
                  </button>
                )}
              </div>
            )}
            {photo?.[1].data.analysis && (
              <p className="small" style={{ color: 'var(--ink-2)' }}>
                Photo check: {photo[1].data.analysis.description}{' '}
                <span className="muted">({String(photo[1].data.analysis.mess_type).replaceAll('_', ' ')}, {photo[1].data.analysis.tier} tier)</span>
              </p>
            )}
            {ev && <Chat ev={ev} />}
            {ev && (ev['ROUTE-COMPARISON'] || ev['PICKUP-PROXIMITY']) && item.category !== 'property_damage' && (
              <div className="sheet" style={{ border: '1px solid var(--hair)', maxWidth: 520 }}><TripMap geo={geoFromEvidence(ev)} id={`s${id}`} /></div>
            )}
          </div>
          {riderArg && driverArg && (
            <div className="section">
              <h3>Both sides</h3>
              <div className="debate">
                {([['rider', riderArg, 'Rider’s advocate'], ['driver', driverArg, 'Driver’s advocate']] as const).map(([r, a, t]) => (
                  <div key={r} className={`side ${r}`}>
                    <span className={`party ${r}`}><i />{t}</span>
                    <ArgText text={a.text} />
                    <div>{a.cites.map((x) => <Cite key={x} caseId={id} refId={x} />)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="section">
            <h3>The AI’s recommendation</h3>
            {!showAI ? (
              <div className="reveal-ai">
                <div>
                  <strong>Look at the evidence first</strong>
                  <p className="small muted">The recommendation stays hidden until you ask, so it doesn’t anchor your judgement.</p>
                </div>
                <button className="btn btn-secondary" onClick={() => setShowAI(true)}><Icon name="eye" size={16} />Show recommendation</button>
              </div>
            ) : dec ? (
              <Verdict caseId={id} dec={dec} />
            ) : (
              <Loading />
            )}
          </div>
        </>
      )}

      {mode === 'change' && (
        <div className="section">
          <h3>{item.is_safety ? 'Record what you did' : 'Change the decision'}</h3>
          <OverrideFields item={item} dec={dec} ev={ev} onChange={setOverride} />
          <div className="reasons" role="group" aria-label="Reason">
            {OVERRIDE_REASONS.map((r) => <button key={r} aria-pressed={reason === r} onClick={() => setReason(r)}>{r}</button>)}
          </div>
          <textarea
            className="input" style={{ minHeight: 90, background: 'var(--surface-2)', border: '1px solid var(--hair)' }}
            placeholder="What you decided, and why" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Note"
          />
        </div>
      )}
      {err && <div className="section"><ErrorNote error={err} /></div>}
      <div className="actionbar">
        <span className="grow">
          {mode === 'change'
            ? 'Your decision and reason are saved next to the AI’s, never over it.'
            : item.is_safety
              ? 'A person decides every safety report.'
              : 'Approving makes the recommendation final and records your name on it.'}
        </span>
        {!item.is_safety && dec && mode !== 'change' && (
          <button className="btn btn-primary" disabled={busy} onClick={approve}>Approve recommendation <kbd>A</kbd></button>
        )}
        {mode !== 'change' ? (
          <button className="btn btn-secondary" onClick={() => setMode('change')}>{item.is_safety ? 'Record outcome' : 'Change decision'} <kbd>C</kbd></button>
        ) : (
          <>
            <button className="btn btn-secondary" onClick={() => setMode(null)}>Cancel</button>
            <button className="btn btn-primary" disabled={busy || !reason || !note.trim() || !override} onClick={save}>Save decision</button>
          </>
        )}
      </div>
    </section>
  )
}

/* What the reviewer decides instead: an outcome, and the remedy the policy allows for it. */
function OverrideFields({
  item, dec, ev, onChange,
}: {
  item: L2QueueItem
  dec: DecisionObject | undefined
  ev: EvidenceIndex | undefined
  onChange: (o: { outcome: Outcome; remedy: Remedy } | null) => void
}) {
  const cat = item.category
  const options: [Outcome, string][] = item.is_safety
    ? [['claim_upheld', 'Report substantiated'], ['claim_denied', 'No action needed']]
    : [['claim_upheld', 'Uphold'], ['claim_upheld_partial', 'Partly uphold'], ['claim_denied', 'Deny']]
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const suggested =
    dec?.remedy.amount ??
    (cat === 'route_deviation' ? ev?.['ROUTE-COMPARISON']?.data.refund_if_unjustified : cat === 'no_show_charge' ? 4.5 : cat === 'property_damage' ? 40 : null)
  const [amount, setAmount] = useState<string>(suggested != null ? String(suggested) : '')

  useEffect(() => {
    if (!outcome) return onChange(null)
    const n = Number(amount)
    let remedy: Remedy
    if (outcome === 'claim_denied' || item.is_safety) remedy = { type: 'no_action' }
    else if (cat === 'no_show_charge') remedy = { type: 'no_show_fee_waiver', amount: n || 4.5, destination: 'original_payment_method' }
    else if (cat === 'property_damage') remedy = { type: 'cleaning_repair_fee', amount: n }
    else remedy = { type: 'partial_refund', amount: n, destination: 'original_payment_method' }
    onChange(remedy.type !== 'no_action' && !(remedy.amount && remedy.amount > 0) ? null : { outcome, remedy })
    // onChange is the parent's state setter
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [outcome, amount])

  const needsAmount = outcome && outcome !== 'claim_denied' && !item.is_safety && cat !== 'no_show_charge'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="reasons" role="group" aria-label="Outcome">
        {options.map(([o, l]) => <button key={o} aria-pressed={outcome === o} onClick={() => setOutcome(o)}>{l}</button>)}
      </div>
      {needsAmount && (
        <label className="small" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {cat === 'property_damage' ? 'Cleaning fee' : 'Refund'}
          {cat === 'property_damage' ? (
            <span className="reasons">
              {[40, 120, 200].map((v) => <button key={v} type="button" aria-pressed={Number(amount) === v} onClick={() => setAmount(String(v))}>{money(v)}</button>)}
            </span>
          ) : (
            <input
              type="number" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)}
              style={{ width: 110, padding: '7px 10px', borderRadius: 10, border: '1px solid var(--line)', font: 'inherit' }}
            />
          )}
        </label>
      )}
      {dec && <p className="tiny muted">The AI recommended: {outcomeLabel(dec.outcome)}{dec.remedy.amount ? ` · ${money(dec.remedy.amount)}` : ''}. Amounts still have to pass the policy’s caps.</p>}
    </div>
  )
}

/* Safety: the case file is prepared on request, with no recommendation. */
function SafetyPrep({ item, ev, prepared, onPrepared }: { item: L2QueueItem; ev: EvidenceIndex | undefined; prepared: boolean; onPrepared: () => void }) {
  const [stage, setStage] = useState<'idle' | 'running' | 'error'>('idle')
  const [err, setErr] = useState<Error | null>(null)
  const { data: view } = useApi(`view:${item.id}`, () => api.caseView(item.id))

  const run = async () => {
    setStage('running')
    try {
      await api.prepareCaseFile(item.id)
      invalidate(`ev:${item.id}`)
      onPrepared()
      setStage('idle')
    } catch (e) {
      setErr(e as Error)
      setStage('error')
    }
  }

  if (!prepared) {
    if (stage === 'running') return <div className="prep-run" aria-live="polite"><span className="spin" />Collecting the trip record, messages, GPS and both histories…</div>
    return (
      <>
        <div className="notice" style={{ background: 'var(--bad-soft)', alignItems: 'center', flexWrap: 'wrap' }}>
          <span className="ic" style={{ background: 'var(--surface)', color: 'var(--bad)' }}><Icon name="shield" size={17} /></span>
          <div style={{ flex: 1, minWidth: 220 }}>
            <strong>No AI has decided anything here</strong>
            <p className="small" style={{ color: 'var(--ink-2)' }}>
              Safety reports skip the hearing. You can have the trip records gathered for you. This prepares a case file only: no advocates, no Judge, no recommendation.
            </p>
          </div>
          <button className="btn btn-primary" onClick={run}><Icon name="file" size={16} />Prepare case file</button>
        </div>
        {err && <ErrorNote error={err} />}
      </>
    )
  }
  if (!ev) return <Loading label="Loading the case file…" />
  const cmp = ev['ROUTE-COMPARISON']?.data
  const comp = ev['PROFILE-COMPLAINER']?.data
  const resp = ev['PROFILE-COMPLAINEE']?.data
  const msgs = Object.entries(ev)
    .filter(([, e]) => e.kind === 'chat_message')
    .map(([k, e]) => ({ k, ...(e.data as { sender_role: 'rider' | 'driver'; timestamp: string; text: string }) }))
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp))
  const start = view?.trip?.scheduled_at
  const end = view?.trip?.completed_at
  return (
    <div className="prepared">
      <div className="prepared-head"><h3 style={{ fontSize: 17 }}>Case file</h3><span className="tag">Assembled in code · evidence only</span></div>
      <div className="sheet" style={{ border: '1px solid var(--hair)', maxWidth: 480 }}><TripMap geo={geoFromEvidence(ev)} id={`p${item.id}`} /></div>
      <ol className="timeline-mini">
        {start && <li><span className="tm">{clock(start)}</span><span>Trip starts</span></li>}
        {msgs.map((m) => (
          <li key={m.k}>
            <span className="tm">{clock(m.timestamp)}</span>
            <span><span className={`party ${m.sender_role}`}><i />{m.sender_role === 'rider' ? 'Rider' : 'Driver'}</span> “{m.text}” <Cite caseId={item.id} refId={m.k} /></span>
          </li>
        ))}
        {end && <li><span className="tm">{clock(end)}</span><span>Trip ends{start ? ` · ${minutesBetween(start, end)} min` : ''}</span></li>}
      </ol>
      <dl className="kv">
        {cmp && <><dt>Distance</dt><dd>{cmp.actual_km.toFixed(1)} km driven, fastest route {cmp.optimal_km.toFixed(1)} km</dd></>}
        {view?.trip?.total_fare != null && <><dt>Fare</dt><dd>{money(view.trip.total_fare)}</dd></>}
        {comp && <><dt>{item.complainer_name}</dt><dd>{comp.dispute_count_30d} dispute{comp.dispute_count_30d === 1 ? '' : 's'} in 30 days · account {comp.account_age_days} days old</dd></>}
        {resp && <><dt>{item.complainee_name}</dt><dd>{resp.dispute_count_30d} dispute{resp.dispute_count_30d === 1 ? '' : 's'} in 30 days · account {resp.account_age_days} days old</dd></>}
      </dl>
      <div className="evidence-grid">{Object.keys(ev).map((r) => <Cite key={r} caseId={item.id} refId={r} />)}</div>
      <p className="tiny muted">Assembled in code from the trip record, with no model call. Nothing here is a recommendation; you decide what happens.</p>
    </div>
  )
}
