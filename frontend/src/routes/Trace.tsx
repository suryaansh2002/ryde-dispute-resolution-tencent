import { Fragment, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import type { Argument, CaseState, DamageFinding, GoldenReport, RecentCase, UsageRow } from '../types/api'
import { api } from '../lib/api'
import { CAT_FULL, day, money, outcomeLabel, secs, statusPill } from '../lib/format'
import {
  agentEvent, agentUsage, argumentOf, buildSteps, caseSeconds, errorOf, gateChecks, isLit, outcomeIcon,
  photoFindings, photoToolOf, preventionOf, STEP_ICON, triageOf, type StepKey,
} from '../lib/hearing'
import { useEvidence, useLiveCase } from '../lib/live'
import { useApi } from '../lib/useApi'
import { Cite, photoUrl } from '../components/evidence'
import { Icon } from '../components/Icon'
import { ArgText, ErrorNote, Loading, Verdict } from '../components/ui'

/* The AI trace, for the judges: each case laid out as a hearing. */

const DOCKET_FILTERS: [string, string][] = [
  ['all', 'All'], ['decided', 'Decided'], ['escalated', 'With a person'],
  ['safety_bypassed', 'Safety'], ['declined_insufficient_evidence', 'Declined'],
]
const DOCKET_MARK: Partial<Record<CaseState, ['check' | 'user' | 'shield' | 'x', string, string]>> = {
  decided: ['check', 'good', 'Decided'],
  escalated: ['user', 'warn', 'With a person'],
  safety_bypassed: ['shield', 'bad', 'Safety team'],
  declined_insufficient_evidence: ['x', 'neutral', 'Declined'],
}

export function Trace({ tab }: { tab: 'cases' | 'accuracy' }) {
  const { caseId } = useParams()
  const navigate = useNavigate()
  const [filter, setFilter] = useState('all')
  const { data: cases, error, reload } = useApi('cases:recent', () => api.recentCases(80), true)
  const { data: featured } = useApi('featured', api.featured)
  const selected = caseId ?? featured?.case_id ?? cases?.[0]?.id ?? null

  return (
    <div className="page">
      <div className="page-title">
        <div>
          <h1>AI trace</h1>
          <p>Each case as a hearing: the complaint, the exhibits, counsel for each side, the bench’s ruling and the clerk’s checks. Hover an exhibit to preview it, click to open it.</p>
        </div>
        <div className="subnav" role="group" aria-label="View">
          <button aria-pressed={tab === 'cases'} onClick={() => navigate(selected ? `/trace/${selected}` : '/trace')}>Docket</button>
          <button aria-pressed={tab === 'accuracy'} onClick={() => navigate('/accuracy')}>Accuracy</button>
        </div>
      </div>
      {tab === 'accuracy' ? (
        <Accuracy />
      ) : (
        <div className="console docket-layout">
          <section className="panel" aria-label="Docket">
            <div className="panel-head"><h2>Docket</h2><span className="small muted num">{cases ? `${cases.length} cases` : ''}</span></div>
            <div className="docket-filter" role="group" aria-label="Filter">
              {DOCKET_FILTERS.map(([k, l]) => <button key={k} aria-pressed={filter === k} onClick={() => setFilter(k)}>{l}</button>)}
            </div>
            {error && <div style={{ padding: '0 16px 16px' }}><ErrorNote error={error} retry={reload} /></div>}
            {!cases && !error && <Loading />}
            <div className="case-list">
              {(cases ?? [])
                .filter((c) => filter === 'all' || c.state === filter)
                .map((c) => <DocketRow key={c.id} c={c} current={c.id === selected} onClick={() => navigate(`/trace/${c.id}`)} />)}
            </div>
          </section>
          {selected ? <CaseTrace key={selected} id={selected} /> : cases && <section className="panel" style={{ padding: 40 }}><p className="muted">No cases yet. File one from the rider or driver app.</p></section>}
        </div>
      )}
    </div>
  )
}

function DocketRow({ c, current, onClick }: { c: RecentCase; current: boolean; onClick: () => void }) {
  const mark = DOCKET_MARK[c.state] ?? (['user', 'neutral', statusPill(c.state)[1]] as const)
  return (
    <button className="inbox-row docket-row" aria-current={current} onClick={onClick}>
      <span className={`mark ${mark[1]}`} title={mark[2]}>
        {DOCKET_MARK[c.state] ? <Icon name={mark[0]} size={13} stroke={2.4} /> : <span className="spin" style={{ width: 12, height: 12 }} />}
        <span className="sr">{mark[2]}</span>
      </span>
      <span className="inbox-main">
        <span className="inbox-t">{c.complainer_name} <span className="vs">v.</span> {c.complainee_name}</span>
        <span className="inbox-why">{c.category ? CAT_FULL[c.category] : 'Not yet filed'} · <span className="mono">{c.id}</span></span>
      </span>
    </button>
  )
}

function ModelDetails({ usage, agent }: { usage: UsageRow[]; agent: string }) {
  const s = agentUsage(usage, agent)
  if (!s) return null
  return (
    <details className="more">
      <summary><Icon name="right" size={14} />Model details</summary>
      <div className="more-body">
        <dl className="kv">
          {s.model && <><dt>Model</dt><dd className="mono">{s.model}</dd></>}
          <dt>Tokens in / out</dt><dd>{s.i.toLocaleString()} / {s.o.toLocaleString()}</dd>
          <dt>Model calls</dt><dd>{s.r}</dd>
          <dt>Tool calls</dt><dd>{s.t}</dd>
          <dt>Time</dt><dd>{secs(s.ms)}</dd>
        </dl>
      </div>
    </details>
  )
}

const OUTCOME_TITLE: Partial<Record<CaseState, [string, string]>> = {
  decided: ['Judgment entered', 'Every final check passed, so the ruling stands without review.'],
  escalated: ['Referred to a person', 'A final check flagged it, so the ruling waits in the support console for a person.'],
  safety_bypassed: ['With the safety team', 'No agent heard this case. It sits at the top of the support console.'],
  declined_insufficient_evidence: ['Declined, can refile', 'The claimant was told exactly what was missing.'],
}

export function CaseTrace({ id }: { id: string }) {
  const [params, setParams] = useSearchParams()
  const live = useLiveCase(id)
  const { view, events, usage, state } = live
  const dec = live.decision?.decision
  const category = view?.category ?? null
  const steps = useMemo(() => (state ? buildSteps(events, state, category) : []), [events, state, category])
  const lit = steps.filter((s) => isLit(s.status)).length
  const evVersion = `${!!agentEvent(events, 'evidence_collection')}${!!photoToolOf(events)}${events.some((e) => e.kind === 'tool_call')}`
  const { data: ev } = useEvidence(view?.has_case_file || agentEvent(events, 'evidence_collection') ? id : null, 'operator', evVersion)

  // Replay: reveal the finished hearing one step at a time.
  const [shown, setShown] = useState<number | null>(null)
  const replaying = shown != null
  useEffect(() => {
    if (shown == null) return
    if (shown >= steps.length) {
      setShown(null)
      return
    }
    const t = setTimeout(() => setShown(shown + 1), shown === 0 ? 400 : 1000)
    return () => clearTimeout(t)
  }, [shown, steps.length])
  // ?replay=1 (the overview's "Watch a hearing") starts it once the case has loaded.
  useEffect(() => {
    if (params.get('replay') && steps.length && !live.live) {
      setShown(0)
      setParams({}, { replace: true })
    }
  }, [params, steps.length, live.live, setParams])

  if (live.error) return <section className="panel" style={{ padding: 28 }}><ErrorNote error={live.error} /></section>
  if (!view || !state) return <section className="panel"><Loading label="Opening the case…" /></section>

  const visibleCount = replaying ? shown : steps.length
  const visible = (key: StepKey) => {
    const i = steps.findIndex((s) => s.key === key)
    return i >= 0 && i < visibleCount && (replaying || isLit(steps[i].status) || steps[i].status === 'now')
  }
  const nodeState = (i: number) => {
    const s = steps[i]
    if (replaying) return i < shown ? s.status : i === shown ? 'now' : 'idle'
    return s.status === 'wait' ? 'idle' : s.status
  }

  const otherRole = view.complainer_role === 'rider' ? 'driver' : 'rider'
  const [pt, pl] = statusPill(state)
  const timing = caseSeconds(events)
  const tokens = usage.reduce((a, u) => a + u.input_tokens + u.output_tokens, 0)
  const calls = usage.reduce((a, u) => a + u.requests, 0)
  const triage = triageOf(events)
  const prevention = preventionOf(events)
  const stopped = !!prevention && !(prevention.detail ?? '').startsWith('prevention: pass')
  const evOut = agentEvent(events, 'evidence_collection')?.output as
    | { chat_log?: unknown[]; gps_trace?: unknown[]; photos?: unknown[]; traffic_events?: unknown[] }
    | undefined
  const tool = photoToolOf(events)
  const findings = photoFindings(events)
  const riderArg = argumentOf(events, 'rider_advocate')
  const driverArg = argumentOf(events, 'driver_advocate')
  const failed = errorOf(events)
  const evRefs = ev ? Object.keys(ev) : []
  const exhibitNo = Object.fromEntries(evRefs.map((r, i) => [r, i + 1]))
  const checks = dec ? gateChecks(dec) : null
  const party = (role: 'rider' | 'driver') => (view.complainer_role === role ? view.complainer_name : view.complainee_name)
  const counsel = (role: 'rider' | 'driver', arg: Argument, agent: string) => (
    <div className={`side ${role} counsel`}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'baseline' }}>
        <span className={`party ${role}`}><i />Counsel for the {role}</span>
        <span className="tiny muted num">self-rated {arg.confidence.toFixed(2)}</span>
      </div>
      <p className="tiny muted" style={{ marginTop: -6 }}>Acting for {party(role)}</p>
      <ArgText text={arg.text} />
      <div>
        {arg.cites.map((x) => <Cite key={x} caseId={id} refId={x} />)}
        {arg.policy_cites.map((x) => <Cite key={x} caseId={id} refId={x} />)}
      </div>
      <ModelDetails usage={usage} agent={agent} />
    </div>
  )
  const reviews = events.filter((e) => e.kind === 'l2_review')

  return (
    <section className="panel" aria-label={`Hearing for ${id}`}>
      <div className="trace-head">
        <p className="small muted docket">Docket <span className="mono">{id}</span> · filed {day(view.created_at)}{category ? ` · ${CAT_FULL[category]}` : ''}</p>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
          <h2 className="caption-title">
            <span className={`party-name ${view.complainer_role}`}>{view.complainer_name}</span> <span className="vs">v.</span>{' '}
            <span className={`party-name ${otherRole}`}>{view.complainee_name}</span>
          </h2>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span className={`pill ${pt}`}>{pl}</span>
            {!live.live && (
              <button className="btn btn-primary btn-sm" onClick={() => setShown(0)} disabled={replaying}>
                <Icon name={replaying ? 'activity' : 'play'} size={14} />
                {replaying ? 'Replaying…' : 'Replay the hearing'}
              </button>
            )}
          </div>
        </div>
        <p className="small muted">The {view.complainer_role} brought the complaint; the {otherRole} responds.</p>
      </div>
      <div className="stats">
        <div className="stat"><b>{timing != null && !live.live ? `${Math.round(timing)} s` : live.live ? 'Live' : '—'}</b><span>Complaint to outcome</span></div>
        <div className="stat"><b>{evRefs.length}</b><span>Exhibits on file</span></div>
        <div className="stat"><b>{calls}</b><span>Model calls</span></div>
        <div className="stat"><b>{tokens ? `${Math.round(tokens / 1000)}K` : '0'}</b><span>Tokens</span></div>
      </div>
      <div className="pipeline" aria-label="Order of proceedings">
        {steps.map((s, i) => (
          <Fragment key={s.key}>
            {i > 0 && <span className={`link${(replaying ? i < (shown ?? 0) : i < lit) ? ' on' : ''}`} />}
            <div className={`node ${s.kind} ${nodeState(i)}`}>
              <span className="node-ic"><Icon name={s.key === 'outcome' ? outcomeIcon(s.status) : STEP_ICON[s.key]} size={17} stroke={2} /></span>
              <span className="nl">{s.label}</span>
              <span className="nt">{s.kind === 'rule' ? 'no AI' : s.kind === 'person' ? '' : 'AI'}</span>
            </div>
          </Fragment>
        ))}
      </div>
      <div className="timeline" aria-live="polite">
        {visible('report') && (
          <div className="step">
            <span className="step-ic"><Icon name="msg" size={18} /></span>
            <div className="step-body">
              <div className="step-title"><h3>The complaint</h3><span className="tag">Never put before the bench</span></div>
              <p style={{ color: 'var(--ink-2)', maxWidth: '72ch' }}>“{view.claim_text}”</p>
              {view.response && (
                <p className="small" style={{ color: 'var(--ink-2)', maxWidth: '72ch' }}>
                  <span className={`party ${otherRole}`}><i />{view.complainee_name} replied</span> “{view.response.text}”
                </p>
              )}
            </div>
          </div>
        )}
        {visible('triage') && (
          <div className="step">
            <span className="step-ic"><Icon name="list" size={18} /></span>
            <div className="step-body">
              <div className="step-title"><h3>Intake</h3><span className="tag">AI</span><span className="t">{secs(agentUsage(usage, 'triage')?.ms)}</span></div>
              {triage ? (
                <p>
                  Filed as {CAT_FULL[triage.category].toLowerCase()}, {triage.tier} severity.{' '}
                  {triage.is_safety ? <strong style={{ color: 'var(--bad)' }}>Safety flag: the case leaves the court and goes to a person.</strong> : 'No safety concern.'}
                </p>
              ) : <p className="muted">Reading the report…</p>}
              <ModelDetails usage={usage} agent="triage" />
            </div>
          </div>
        )}
        {visible('rules') && prevention && (
          <div className="step rule">
            <span className="step-ic"><Icon name="check" size={18} /></span>
            <div className="step-body">
              <div className="step-title"><h3>Clerk’s checks</h3><span className="tag rule">Plain code, no AI</span></div>
              <p>
                {stopped
                  ? (prevention.detail ?? '').includes('safety')
                    ? 'Safety hard stop: no agent hears this case. It goes straight to the safety team.'
                    : (prevention.detail ?? '').includes('stale')
                      ? 'Outside the 30-day window: declined, not denied.'
                      : 'Required evidence missing: declined, not denied. The claimant can refile with a photo.'
                  : `All six checks passed: not a duplicate, well formed, not safety, evidence present, within 30 days${(prevention.detail ?? '').includes('repeat filer') ? ', repeat filer flagged' : ', filer history noted'}.`}
              </p>
            </div>
          </div>
        )}
        {visible('evidence') && (
          <div className="step">
            <span className="step-ic"><Icon name="file" size={18} /></span>
            <div className="step-body">
              <div className="step-title"><h3>Exhibits entered</h3><span className="tag">AI</span><span className="t">{secs(agentUsage(usage, 'evidence_collection')?.ms)}</span></div>
              {evOut ? (
                <>
                  <p>
                    The only agent allowed to read raw records. It entered {evRefs.length} exhibits: {evOut.gps_trace?.length ?? 0} GPS fixes, {evOut.chat_log?.length ?? 0} messages,{' '}
                    {evOut.photos?.length ?? 0} photo{evOut.photos?.length === 1 ? '' : 's'}, the fare and both histories. Counsel on both sides gets the identical set.
                  </p>
                  <ol className="exhibits">
                    {evRefs.map((r) => <li key={r}><span className="ex-no">Exhibit {exhibitNo[r]}</span><Cite caseId={id} refId={r} /></li>)}
                  </ol>
                </>
              ) : <p className="muted">Collecting the trip records…</p>}
              <ModelDetails usage={usage} agent="evidence_collection" />
            </div>
          </div>
        )}
        {visible('photo') && (
          <div className="step">
            <span className="step-ic"><Icon name="camera" size={18} /></span>
            <div className="step-body">
              <div className="step-title"><h3>Photo examined</h3><span className="tag">AI vision</span><span className="t">{secs(tool?.latency_ms)}</span></div>
              {!tool && <p className="muted">Looking at the photo…</p>}
              {Object.entries(findings).map(([ref, f]: [string, DamageFinding]) => (
                <div key={ref} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 200px) minmax(0, 1fr)', gap: 16, alignItems: 'start' }}>
                  <div className="photo">{ev?.[ref] && <img src={photoUrl(ev[ref])} alt="Damage photo" />}</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <p>{f.description}</p>
                    <dl className="kv">
                      <dt>What it shows</dt><dd>{f.mess_type.replaceAll('_', ' ')}, {f.extent} area</dd>
                      <dt>Fee tier</dt><dd>{f.tier}{({ minor: 40, moderate: 120, severe: 200 } as Record<string, number>)[f.tier] ? ` · ${money(({ minor: 40, moderate: 120, severe: 200 } as Record<string, number>)[f.tier])}` : ''}</dd>
                      <dt>Confidence</dt><dd>{f.confidence.toFixed(2)}</dd>
                    </dl>
                    <p className="tiny muted">The model only says what it sees. The tier comes from Ryde’s fee table, in code.</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        {visible('hearing') && (
          <div className="step">
            <span className="step-ic"><Icon name="scale" size={18} /></span>
            <div className="step-body">
              <div className="step-title"><h3>The hearing</h3><span className="tag">Two AI counsel, in parallel</span><span className="t">{secs(agentEvent(events, 'rider_advocate')?.latency_ms)}</span></div>
              {riderArg && driverArg ? (
                <div className="courtroom">
                  {visible('judge') && dec && (
                    <div className="bench-bar"><span><Icon name="gavel" size={15} />The bench</span><span className="tiny muted">Reads both arguments and the exhibits. Never the complaint.</span></div>
                  )}
                  <div className="debate">
                    {counsel('rider', riderArg, 'rider_advocate')}
                    {counsel('driver', driverArg, 'driver_advocate')}
                  </div>
                </div>
              ) : <p className="muted">Both counsel are preparing their arguments…</p>}
              <p className="hearing-note"><Icon name="info" size={15} />Any citation that isn’t an exhibit on file is struck before the bench sees the argument.</p>
            </div>
          </div>
        )}
        {visible('judge') && (
          <div className="step">
            <span className="step-ic"><Icon name="gavel" size={18} /></span>
            <div className="step-body">
              <div className="step-title"><h3>The bench rules</h3><span className="tag">AI</span><span className="t">{secs(agentEvent(events, 'judge')?.latency_ms)}</span></div>
              {dec ? (
                <>
                  <Verdict caseId={id} dec={dec} court />
                  <p className="tiny muted">Dollar amounts the policy fixes are computed in code, not by the Judge.</p>
                </>
              ) : <p className="muted">The bench is weighing both arguments…</p>}
              <ModelDetails usage={usage} agent="judge" />
            </div>
          </div>
        )}
        {visible('gates') && checks && (
          <div className="step rule">
            <span className="step-ic"><Icon name="check" size={18} /></span>
            <div className="step-body">
              <div className="step-title"><h3>Final checks</h3><span className="tag rule">Plain code, no AI</span></div>
              <div className="checks">
                {checks.map(([ok, t, s]) => (
                  <div key={t} className={`check-row ${ok ? 'pass' : 'flag'}`}>
                    <span className="ci"><Icon name={ok ? 'check' : 'alert'} size={13} stroke={2.6} /></span>
                    <div><strong>{t}</strong><small>{s}</small></div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
        {visible('outcome') && OUTCOME_TITLE[state] && (
          <div className="step">
            <span
              className="step-ic"
              style={{
                background: state === 'decided' ? 'var(--good-soft)' : state === 'declined_insufficient_evidence' ? 'var(--fill)' : state === 'safety_bypassed' ? 'var(--bad-soft)' : 'var(--warn-soft)',
                border: 0,
              }}
            >
              <Icon name={state === 'decided' ? 'check' : 'user'} size={18} />
            </span>
            <div className="step-body">
              <div className="step-title"><h3>{reviews.length ? 'Decided by a person' : OUTCOME_TITLE[state]![0]}</h3></div>
              <p className="muted">
                {reviews.length
                  ? `${reviews[reviews.length - 1].detail ?? 'A reviewer decided this case.'}`
                  : OUTCOME_TITLE[state]![1]}
              </p>
              {state === 'escalated' && <Link className="btn btn-secondary btn-sm" style={{ alignSelf: 'flex-start' }} to={`/support/${id}`}>Open in the support console</Link>}
              {state === 'safety_bypassed' && <Link className="btn btn-secondary btn-sm" style={{ alignSelf: 'flex-start' }} to={`/support/${id}`}>Open in the support console</Link>}
            </div>
          </div>
        )}
        {failed && (
          <div className="step">
            <span className="step-ic" style={{ background: 'var(--bad-soft)', color: 'var(--bad)', border: 0 }}><Icon name="alert" size={18} /></span>
            <div className="step-body">
              <div className="step-title"><h3>Something failed</h3></div>
              <p className="small" style={{ color: 'var(--ink-2)', wordBreak: 'break-word' }}>{failed.detail}</p>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}

function Accuracy() {
  const { data: g, error, reload } = useApi<GoldenReport>('golden', api.golden, true)
  const [starting, setStarting] = useState(false)
  const running = g?.status.running
  useEffect(() => {
    if (!running) return
    const t = setInterval(reload, 4000)
    return () => clearInterval(t)
  }, [running, reload])
  const start = async () => {
    setStarting(true)
    try {
      await api.startGolden()
      reload()
    } finally {
      setStarting(false)
    }
  }
  if (error) return <ErrorNote error={error} retry={reload} />
  if (!g) return <section className="panel"><Loading /></section>
  const cats = Object.entries(g.by_category)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <section className="panel acc-panel">
        <div>
          <div className="acc-big">{g.passed}/{g.total}</div>
          <p style={{ fontSize: 18, marginTop: 14, color: 'var(--ink-2)', maxWidth: '36ch' }}>
            Labelled cases where the verdict matched the label: outcome, remedy and exact amount. Each was filed through the full pipeline with real model calls.
          </p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <div className="cat-bars">
            {cats.map(([k, b]) => (
              <div key={k} className="cat-bar">
                <span>{CAT_FULL[k as keyof typeof CAT_FULL]}</span>
                <span className="bar"><i style={{ width: `${b!.run ? (b!.passed / b!.run) * 100 : 0}%` }} /></span>
                <span className="num" style={{ textAlign: 'right' }}>{b!.passed}/{b!.run}</span>
              </div>
            ))}
          </div>
          <dl className="kv" style={{ marginTop: 6 }}>
            <dt>Decided with no person</dt><dd>{g.decided_automatically} of {g.run}</dd>
            <dt>Sent to a person</dt><dd>{g.sent_to_a_person} (safety, high-value, repeat filers)</dd>
            {g.median_seconds != null && <><dt>Median time per case</dt><dd>{Math.round(g.median_seconds)} s</dd></>}
          </dl>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <button className="btn btn-secondary btn-sm" disabled={running || starting} onClick={start}>
              <Icon name={running ? 'activity' : 'play'} size={14} />
              {running ? `Running ${g.status.done}/${g.status.total}…` : 'Run all cases again'}
            </button>
            <span className="tiny muted">Files every labelled case for real. Takes a few minutes and about 300 model calls.</span>
          </div>
        </div>
      </section>
      <section className="panel">
        <div className="panel-head"><h2>Every labelled case</h2><span className="tiny muted">Labels written from the synthetic data’s ground truth</span></div>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>Case</th><th>Category</th><th>Label</th><th>System said</th><th>Result</th><th className="r">Time</th></tr></thead>
            <tbody>
              {g.cases.map((c) => {
                const r = c.result
                const a = r?.actual
                const said = !a ? '—' : a.state === 'safety_bypassed' ? 'To the safety team' : a.outcome ? `${outcomeLabel(a.outcome)}${a.remedy?.amount ? ` · ${money(a.remedy.amount)}` : ''}` : a.state === 'declined_insufficient_evidence' ? 'Declined, can refile' : a.error ? 'Error' : a.state ?? '—'
                const label = c.expected.outcome === 'escalated_to_l2' ? 'To the safety team' : `${outcomeLabel(c.expected.outcome)}${c.expected.remedy?.amount ? ` · ${money(c.expected.remedy.amount)}` : ''}`
                return (
                  <tr key={c.golden_id}>
                    <td>{r?.case_id ? <Link className="mono" to={`/trace/${r.case_id}`}>{r.case_id}</Link> : <span className="mono muted">{c.golden_id}</span>}</td>
                    <td>{CAT_FULL[c.category]}</td>
                    <td>{label}</td>
                    <td>{said}</td>
                    <td>{r ? <span className={`pill ${r.passed ? 'good' : 'bad'}`}>{r.passed ? 'Match' : 'Mismatch'}</span> : <span className="pill neutral">Not run</span>}</td>
                    <td className="r">{r ? `${Math.round(r.seconds)} s` : ''}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
