import { Link, useNavigate } from 'react-router-dom'
import type { Argument } from '../types/api'
import { api } from '../lib/api'
import { CAT_FULL, money, outcomeLabel, secs } from '../lib/format'
import { agentEvent, agentUsage, argumentOf } from '../lib/hearing'
import { useLiveCase } from '../lib/live'
import { useApi } from '../lib/useApi'
import { Cite } from '../components/evidence'
import { Icon, type IconName } from '../components/Icon'
import { Outcome } from '../components/party'
import { POLICY_INFO } from '../components/PolicyView'
import { Phone } from '../components/ui'

/* The landing page: the rider's outcome next to the hearing behind it, the transcript of
   both counsel, who decides what, and the measured accuracy. All of it live data. */

/** The argument's first plain-language sentence, for the transcript excerpt: skips
 * sentences that quote raw field names (add_on_fees) or are too short to stand alone. */
function lead(text: string) {
  // Split only where a sentence really ends: punctuation, space, then a capital ("$2.48" stays whole).
  const sentences = text.split(/(?<=[.!?])\s+(?=[A-Z“"(])/).map((x) => x.trim()).filter(Boolean)
  const found = sentences.find((x) => x.length > 60 && !/\w_\w/.test(x)) ?? sentences[0]
  // Inline ref lists like "(ROUTE-COMPARISON, GPS-TRACE)" become the footnotes instead.
  const s = found.replace(/\s*\((?:[A-Z]+(?:-[A-Z0-9]+)+(?:,\s*)?)+\)/g, '')
  return s.length > 260 ? `${s.slice(0, 257).trimEnd()}…` : s
}

export function Overview() {
  const navigate = useNavigate()
  const { data: featured } = useApi('featured', api.featured)
  const id = featured?.case_id ?? null
  const live = useLiveCase(id)
  const { data: queue } = useApi('l2:queue', api.l2Queue, true)
  const { data: g } = useApi('golden', api.golden)

  const riderArg = argumentOf(live.events, 'rider_advocate')
  const driverArg = argumentOf(live.events, 'driver_advocate')
  const dec = live.decision?.decision
  const view = live.view

  const riderCites = riderArg?.cites.slice(0, 2) ?? []
  const driverCites = [...(driverArg?.cites ?? []).slice(0, 1), ...(driverArg?.policy_cites ?? []).slice(0, 1)]
  const safetyN = queue?.filter((q) => q.is_safety).length ?? 0
  const highN = queue?.filter((q) => q.escalation?.bucket_escalate && !q.is_safety).length ?? 0
  const otherN = (queue?.length ?? 0) - safetyN - highN

  const mini: [IconName, string, string, 'ai' | 'rule'][] = id
    ? [
        ['msg', 'Report received', '', 'ai'],
        ['list', 'Triage', secs(agentUsage(live.usage, 'triage')?.ms), 'ai'],
        ['check', 'Prevention rules', 'no AI', 'rule'],
        ['search', 'Evidence collected', secs(agentUsage(live.usage, 'evidence_collection')?.ms), 'ai'],
        ['scale', 'Advocates argue', secs(agentEvent(live.events, 'rider_advocate')?.latency_ms), 'ai'],
        ['gavel', 'Judge rules', secs(agentEvent(live.events, 'judge')?.latency_ms), 'ai'],
        ['check', 'Gates pass', 'no AI', 'rule'],
      ]
    : []

  return (
    <div>
      <section className="ov-hero">
        <div>
          <h1>Every ride dispute,<br />heard fairly.</h1>
          <p className="lede">
            One AI advocate for the <span style={{ color: 'var(--rider)', fontWeight: 600 }}>rider</span>, one for the{' '}
            <span style={{ color: 'var(--driver)', fontWeight: 600 }}>driver</span>, a judge that cites every fact, and plain-code checks that hand anything uncertain or unsafe to a person.
          </p>
          <div className="ctas">
            <Link className="btn btn-primary" to="/rider"><Icon name="phone" size={16} />File as a rider</Link>
            <Link className="btn btn-primary" to="/driver?start=damage"><Icon name="car" size={16} />File as a driver</Link>
            {id && <Link className="btn btn-quiet" to={`/trace/${id}?replay=1`}><Icon name="play" size={15} />Watch a hearing</Link>}
          </div>
        </div>
        {id && (
          <div className="hero-visual">
            <Phone small>
              <Outcome caseId={id} viewer={view?.complainer_role ?? 'rider'} claimText={view?.claim_text} />
            </Phone>
            <div className="mini-trace">
              <h3>Behind that screen</h3>
              {mini.map(([ic, l, t, k]) => (
                <div key={l} className={`mini-row ${k}`}>
                  <span className="mi"><Icon name={ic} size={12} stroke={2.4} /></span>
                  <span>{l}</span>
                  <span className="mt">{t}</span>
                </div>
              ))}
              <Link className="btn btn-quiet btn-sm" style={{ alignSelf: 'flex-start', marginTop: 6 }} to={`/trace/${id}`}>
                Open the full trace <Icon name="arrow" size={14} />
              </Link>
            </div>
          </div>
        )}
      </section>

      {id && riderArg && driverArg && dec && (
        <section className="ov-band">
          <div>
            <h2>Both sides get an advocate.</h2>
            <p className="lede">Two agents argue the same case from the identical evidence file. Every factual claim has to cite a real item in it, or it’s stripped.</p>
          </div>
          <div className="transcript">
            <Excerpt caseId={id} role="rider" arg={riderArg} cites={riderCites} n={1} />
            <Excerpt caseId={id} role="driver" arg={driverArg} cites={driverCites} n={1 + riderCites.length} />
            <div className="ruling-line">
              <div>
                <span className="muted small">The bench, which never reads the complaint</span>
                <p>
                  <strong>{outcomeLabel(dec.outcome)}.</strong>
                  {dec.remedy.amount ? ` ${money(dec.remedy.amount)} ${dec.remedy.type === 'cleaning_repair_fee' ? 'cleaning fee' : 'back to the rider'}.` : ''}
                </p>
              </div>
              <Link className="btn btn-quiet" to={`/trace/${id}`}>Read the ruling <Icon name="arrow" size={14} /></Link>
            </div>
            <ol className="footnotes">{[...riderCites, ...driverCites].map((c, i) => <li key={`${c}${i}`}>{describeRef(c)}</li>)}</ol>
            <p className="tiny muted">
              Opening lines from <span className="mono">{id}</span>{view?.category ? `, a ${CAT_FULL[view.category].toLowerCase()} case` : ''}. Hover a number to preview the evidence, click to open it.
            </p>
          </div>
        </section>
      )}

      <section className="ov-band">
        <div>
          <h2>Some decisions belong to people.</h2>
          <p className="lede">Plain-code checks run on every decision, whatever the AI says. Right now {queue?.length ?? '…'} cases wait for a person.</p>
        </div>
        <div className="people-list">
          <div className="people-row"><b style={{ color: 'var(--bad)' }}>{safetyN}</b><div><h3>Safety reports</h3><p>Never seen by any agent. They go straight to the safety team.</p></div><span /></div>
          <div className="people-row"><b style={{ color: 'var(--warn)' }}>{highN}</b><div><h3>High stakes and repeat filers</h3><p>Cleaning fees of $120 or more, and anyone with three disputes in 30 days.</p></div><span /></div>
          <div className="people-row"><b>{otherN}</b><div><h3>Rule checks and uncertain calls</h3><p>Confidence under 0.60, a Judge asking for help, or a remedy that breaks a policy cap.</p></div><span /></div>
          <div style={{ paddingTop: 18 }}><Link className="btn btn-secondary" to="/support">Open the support console</Link></div>
        </div>
      </section>

      {g && g.run > 0 && (
        <section className="ov-band">
          <div>
            <h2>Measured, not claimed.</h2>
            <p className="lede">{g.total} labelled cases, filed through the full pipeline with real model calls. Each verdict is checked against its label down to the cent.</p>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
            <div className="acc-big">{g.passed}/{g.total}</div>
            <div className="cat-bars">
              {Object.entries(g.by_category).map(([k, b]) => (
                <div key={k} className="cat-bar">
                  <span>{CAT_FULL[k as keyof typeof CAT_FULL]}</span>
                  <span className="bar"><i style={{ width: `${b!.run ? (b!.passed / b!.run) * 100 : 0}%` }} /></span>
                  <span className="num" style={{ textAlign: 'right' }}>{b!.passed}/{b!.run}</span>
                </div>
              ))}
            </div>
            <div><Link className="btn btn-secondary" to="/accuracy">See every case</Link></div>
          </div>
        </section>
      )}

      <section className="ov-band" style={{ paddingBottom: 40 }}>
        <div>
          <h2>Four apps, one system.</h2>
          <p className="lede">Each role gets its own app. All of them run on the same cases.</p>
        </div>
        <div className="doors">
          {([
            ['phone', 'Rider app', 'File a dispute from a trip and follow it to the outcome.', '/rider'],
            ['car', 'Driver app', 'Answer a report, or file your own cleaning-fee claim.', '/driver'],
            ['headset', 'Support console', 'Decide what the checks flagged. Evidence first, AI second.', '/support'],
            ['activity', 'AI trace', 'Every agent, every citation, every rule, for any case.', '/trace'],
          ] as [IconName, string, string, string][]).map(([ic, t, d, to]) => (
            <button key={t} className="door" onClick={() => navigate(to)}>
              <span className="di"><Icon name={ic} size={22} /></span>
              <span><h3>{t}</h3><p>{d}</p></span>
              <Icon name="right" size={18} style={{ color: 'var(--ink-4)' }} />
            </button>
          ))}
        </div>
      </section>
      <footer className="ov-foot">
        RydeResolve is a dispute resolution system built for Ryde, for the Tencent hackathon. It isn’t an official Ryde product. All riders, drivers and trips are synthetic. Cases, arguments, rulings and timings are real output of the pipeline.
      </footer>
    </div>
  )
}

/** What a cited item is, for the transcript's footnotes. */
function describeRef(ref: string) {
  if (ref === 'ROUTE-COMPARISON') return 'Route comparison, computed from the trip’s GPS'
  if (ref === 'ROUTE-ACTUAL') return 'Route driven'
  if (ref === 'ROUTE-OPTIMAL') return 'Fastest route'
  if (ref === 'PICKUP-PROXIMITY') return 'How close the driver came to the pickup, from GPS'
  if (ref === 'GPS-TRACE') return 'The driver’s GPS record'
  if (ref === 'PAYMENT') return 'The fare receipt'
  if (ref.startsWith('MSG-')) return 'A message sent during the trip'
  if (ref.startsWith('EV-')) return 'The photo filed with the report'
  if (ref.startsWith('TRAFFIC-')) return 'A traffic record near the route'
  if (ref.startsWith('PROFILE-')) return 'Dispute history'
  if (ref.startsWith('POL-')) return `${POLICY_INFO[ref.slice(0, 6)]?.[0] ?? 'Dispute'} policy`
  return ref
}

function Excerpt({ caseId, role, arg, cites, n }: { caseId: string; role: 'rider' | 'driver'; arg: Argument; cites: string[]; n: number }) {
  return (
    <figure className="tq">
      <figcaption><span className={`party ${role}`}><i />Counsel for the {role}</span></figcaption>
      <blockquote>
        “{lead(arg.text)}”
        {cites.map((c, i) => <Cite key={c} caseId={caseId} refId={c} n={n + i} />)}
      </blockquote>
    </figure>
  )
}
