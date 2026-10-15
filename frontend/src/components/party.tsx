import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { CaseState, Category, Role, TraceEvent } from '../types/api'
import { api } from '../lib/api'
import type { TriageResult } from '../types/api'
import { CAT, day, first, isFinal, money } from '../lib/format'
import { agentEvent, errorOf, photoToolOf, preventionOf } from '../lib/hearing'
import { useApi } from '../lib/useApi'
import { Icon } from './Icon'
import { FactSheet, Loading, Notice, ResultHero } from './ui'

/* What a rider or driver sees. No AI anywhere in here: plain stages, plain outcomes. */

export type IssueKind = 'route' | 'noshow' | 'damage' | 'safety'

export const KIND_CATEGORY: Record<IssueKind, Category> = {
  route: 'route_deviation',
  noshow: 'no_show_charge',
  damage: 'property_damage',
  safety: 'safety_incident',
}

const ISSUES: Record<Role, { key: IssueKind; label: string }[]> = {
  rider: [
    { key: 'route', label: 'The driver took a longer route' },
    { key: 'noshow', label: 'I was charged a no-show fee' },
    { key: 'safety', label: 'I felt unsafe' },
  ],
  driver: [
    { key: 'damage', label: 'The rider left a mess in my car' },
    { key: 'noshow', label: 'The rider didn’t show up' },
    { key: 'safety', label: 'I felt unsafe' },
  ],
}

/** Example words for the demo, so nobody has to improvise a complaint on camera. */
export const EXAMPLE_CLAIM: Record<Role, Partial<Record<IssueKind, string>>> = {
  rider: {
    route: 'The driver took a route that was much longer than necessary and I was charged extra for it. The detour doesn’t make sense for this trip.',
    noshow: 'I was charged a no-show fee, but I was waiting at the pickup point the whole time and the driver never arrived.',
    safety: 'The driver was driving recklessly and ran two red lights. I felt unsafe the entire trip.',
  },
  driver: {
    damage: 'The rider spilled something and left mud and dirt all over the back seat and floor. I had to take the car to be cleaned.',
    noshow: 'I waited at the pickup point for more than five minutes and called the rider, but they never came.',
    safety: 'The rider was aggressive and threatening during the trip. I felt unsafe.',
  },
}

export const EXAMPLE_REPLY: Partial<Record<Category, string>> = {
  route_deviation: 'There was a road closure on the usual way, so I followed the app’s detour.',
  no_show_charge: 'I was at the pickup point on time and waited, but I couldn’t find the rider.',
  property_damage: 'The car was already like that when I got in. I didn’t make any mess.',
}

/* Fallback only, for when the Triage agent can't be reached: a keyword guess, so the chat
   still answers. Filing runs the real Triage agent either way. */
function guessKind(text: string): IssueKind | null {
  const t = text.toLowerCase()
  if (/unsafe|threat|aggress|scared|danger|assault|harass|drunk|red light|reckless/.test(t)) return 'safety'
  if (/vomit|spill|mess|dirt|mud|stain|clean|seat/.test(t)) return 'damage'
  if (/no.?show|didn'?t show|never (came|showed|arrived)|cancel|waited|fee/.test(t)) return 'noshow'
  if (/route|longer|detour|way round|long way|extra|distance|overcharg/.test(t)) return 'route'
  return null
}

const BOT_REPLY: Record<IssueKind, (other: string, who: Role) => string> = {
  route: (o) => `That sounds like the route was longer than it needed to be. I’ve attached your trip’s GPS record, the fastest route, your messages with ${first(o)} and the fare.`,
  noshow: (o, who) =>
    who === 'driver'
      ? `Sounds like ${first(o)} didn’t come to the pickup. I’ve attached your GPS near the pickup, your messages and the trip record.`
      : `Sounds like you were charged a no-show fee you don’t think is fair. I’ve attached ${first(o)}’s GPS near your pickup, your messages and the charge.`,
  damage: () => 'Sorry about that. Cleaning fees need at least one photo of the mess. Add one and I’ll attach it with the trip record and your messages.',
  safety: () => 'Thank you for telling us. I’m passing this straight to our safety team. A person, not an automated system, will contact you. If you’re in danger right now, call 999.',
}

interface Msg {
  from: 'bot' | 'me'
  text: string
  photo?: string
  choices?: boolean
  attach?: boolean
}

export interface IntakeResult {
  kind: IssueKind
  text: string
  photo: Blob | null
}

const kindOf = (t: TriageResult): IssueKind =>
  t.is_safety ? 'safety' : (Object.entries(KIND_CATEGORY).find(([, c]) => c === t.category)?.[0] as IssueKind)

/** What the chat heard: the Triage agent's reading of the person's own words, or the
 * keyword fallback when the agent is unavailable. */
async function hear(tripId: string, text: string): Promise<IssueKind | null> {
  const started = Date.now()
  let kind: IssueKind | null
  try {
    kind = kindOf(await api.intakeTriage(tripId, text))
  } catch {
    kind = guessKind(text)
  }
  // A beat of "typing" even when the answer is instant, so the reply doesn't feel canned.
  const wait = 700 - (Date.now() - started)
  if (wait > 0) await new Promise((r) => setTimeout(r, wait))
  return kind
}

export function ChatIntake({
  tripId,
  who,
  me,
  other,
  tripDate,
  fare,
  suggested,
  samplePhoto,
  onReview,
}: {
  tripId: string
  who: Role
  me: string
  other: string
  tripDate: string | null
  fare: number | null
  /** The scenario's kind of issue, for the example words. */
  suggested: IssueKind | null
  samplePhoto: string | null
  onReview: (r: IntakeResult) => void
}) {
  const [msgs, setMsgs] = useState<Msg[]>([
    { from: 'bot', text: `Hi ${first(me)}. What went wrong on your ${day(tripDate)} trip with ${first(other)}?` },
  ])
  const [draft, setDraft] = useState('')
  const [kind, setKind] = useState<IssueKind | null>(null)
  const [typing, setTyping] = useState(false)
  const [photo, setPhoto] = useState<{ url: string; blob: Blob } | null>(null)
  const [noPhoto, setNoPhoto] = useState(false)
  const [words, setWords] = useState<string[]>([])
  const logRef = useRef<HTMLDivElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [msgs, typing, photo])

  const say = async (text: string, picked?: IssueKind) => {
    if (!text.trim() || typing) return
    setMsgs((m) => [...m, { from: 'me', text }])
    if (!picked) setWords((w) => [...w, text])
    setDraft('')
    setTyping(true)
    // A tapped choice is the person's own answer; typed words go to the Triage agent.
    const k = picked ?? (await hear(tripId, [...words, text].join(' ')))
    setTyping(false)
    if (!k) {
      setMsgs((m) => [...m, { from: 'bot', text: 'Thanks. Which of these is closest?', choices: true }])
      return
    }
    setKind(k)
    setMsgs((m) => [...m, { from: 'bot', text: BOT_REPLY[k](other, who), attach: k !== 'safety' && k !== 'damage' }])
  }

  const attach = (blob: Blob) => {
    const url = URL.createObjectURL(blob)
    setPhoto({ url, blob })
    setMsgs((m) => [
      ...m,
      { from: 'me', text: '', photo: url },
      { from: 'bot', text: 'Got it. The photo check looks at it once you send. I’ve also attached the trip record and your messages.' },
    ])
  }
  const useSample = async () => {
    if (!samplePhoto) return fileRef.current?.click()
    const res = await fetch(samplePhoto)
    attach(await res.blob())
  }

  const lastBot = [...msgs].reverse().find((m) => m.from === 'bot')
  const showChoices = !kind && (msgs.length === 1 || !!lastBot?.choices)
  const ready = kind && (kind !== 'damage' || photo || noPhoto)
  // What gets filed is what the person typed; a tapped choice stands in when they typed nothing.
  const claimText = () =>
    words.join(' ').trim() || ISSUES[who].find((o) => o.key === kind)?.label || ''
  const example = EXAMPLE_CLAIM[who][suggested ?? 'route'] ?? Object.values(EXAMPLE_CLAIM[who])[0]

  return (
    <div className="app-view" style={{ overflow: 'hidden' }}>
      <div className="app-head" style={{ paddingBottom: 8 }}>
        <h2 style={{ fontSize: 24 }}>Report a problem</h2>
        <p className="small muted">{day(tripDate)} trip · {money(fare)}</p>
      </div>
      <div className="chatlog" ref={logRef} aria-live="polite">
        {msgs.map((m, i) => (
          <div key={i} className={`msg ${m.from === 'me' ? `me ${who}` : 'bot'}${m.photo ? ' photo-msg' : ''}`}>
            {m.photo ? <img src={m.photo} alt="Your photo" /> : m.text}
            {m.attach && (
              <div className="msg-attach">
                {([['pin', 'GPS record'], ['route', 'Fastest route and route driven'], ['msg', 'Your messages'], ['receipt', 'Fare receipt']] as const).map(([ic, t]) => (
                  <span key={t}><Icon name={ic} size={13} />{t}</span>
                ))}
              </div>
            )}
          </div>
        ))}
        {kind === 'damage' && !photo && !noPhoto && (
          <>
            <button className="msg-action" onClick={useSample}><Icon name="photoAdd" size={16} />Add a photo</button>
            <button className="use-example" style={{ alignSelf: 'flex-end' }} onClick={() => fileRef.current?.click()}>Choose your own photo</button>
            <button className="use-example" style={{ alignSelf: 'flex-end' }} onClick={() => setNoPhoto(true)}>Send without a photo</button>
            <input
              ref={fileRef} type="file" accept="image/*" hidden
              onChange={(e) => { const f = e.target.files?.[0]; if (f) attach(f) }}
            />
          </>
        )}
        {typing && <div className="msg bot typing" aria-label="Typing"><i /><i /><i /></div>}
        {showChoices && (
          <div className="quick">
            {ISSUES[who].map((o) => (
              <button key={o.key} className={o.key === 'safety' ? 'safety' : ''} onClick={() => say(o.label, o.key)}>{o.label}</button>
            ))}
          </div>
        )}
      </div>
      {ready ? (
        <div className="app-footer">
          <button className="btn btn-primary btn-block" onClick={() => onReview({ kind: kind!, text: claimText(), photo: photo?.blob ?? null })}>
            {kind === 'safety' ? 'Send to the safety team' : 'Review and send'}
          </button>
        </div>
      ) : (
        <form className="composer" onSubmit={(e) => { e.preventDefault(); say(draft) }}>
          {!kind && <button type="button" className="use-example" onClick={() => setDraft(example)}>Use example words</button>}
          <div className="composer-row">
            <textarea
              rows={2} placeholder="Tell us what happened" value={draft} aria-label="Message"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); say(draft) } }}
            />
            <button type="submit" className="send" disabled={!draft.trim()} aria-label="Send">
              <Icon name="arrow" size={18} stroke={2.4} style={{ transform: 'rotate(-90deg)' }} />
            </button>
          </div>
        </form>
      )}
    </div>
  )
}

/** The rule for each kind of dispute, in plain words, shown before sending. */
export const RULE: Record<Category, string> = {
  route_deviation: 'If a trip is much longer than the fastest route and nothing on record explains it, the fare for the extra distance is refunded: half of it between 10% and 25% longer, all of it above 25%.',
  no_show_charge: 'A no-show fee only applies if the driver arrived within 100 m of the pickup, waited the required time, and tried to reach the rider.',
  property_damage: 'The photo sets the fee: $40 for a spill or crumbs, $120 for mud, dirt or stains, $200 for vomit.',
  safety_incident: 'Safety reports are always handled by a person.',
}

export function FeeTable({ note }: { note?: string }) {
  return (
    <div className="sheet">
      <h4>Fees by what the photo shows</h4>
      <dl className="kv" style={{ padding: '10px 16px 6px' }}>
        <dt>Spill or crumbs</dt><dd>{money(40)}</dd>
        <dt>Mud, dirt or stains</dt><dd>{money(120)}</dd>
        <dt>Vomit</dt><dd>{money(200)}</dd>
      </dl>
      <p className="tiny muted" style={{ padding: '0 16px 14px' }}>{note ?? 'Ryde’s published cleaning-fee tiers. The photo sets the tier, not the description.'}</p>
    </div>
  )
}

/* Live progress in plain stages, driven by the case's own trace events. */

type Stage = [string, string, (e: TraceEvent[], s: CaseState) => boolean]

const has = (agent: Parameters<typeof agentEvent>[1]) => (e: TraceEvent[]) => !!agentEvent(e, agent)
const past = (...states: CaseState[]) => (_: TraceEvent[], s: CaseState) => !states.includes(s)

function stagesFor(viewerSide: 'complainer' | 'complainee', other: string, category: Category | null, safety: boolean): Stage[] {
  if (safety)
    return [
      ['Report received', '', () => true],
      ['Sent to our safety team', 'A person handles this', (_, s) => s === 'safety_bypassed'],
    ]
  const stages: Stage[] = [
    ['Report received', '', () => true],
    ['Checking eligibility', 'Quick automatic checks', (e) => !!preventionOf(e)],
    [
      'Gathering trip records',
      category === 'property_damage' ? 'Trip, messages and the photo' : 'GPS, route, fare, messages',
      has('evidence_collection'),
    ],
  ]
  if (category === 'property_damage')
    stages.push(['Photo check', 'What the photo shows sets the fee tier', (e) => !!photoToolOf(e)])
  stages.push(
    viewerSide === 'complainer'
      ? [`${first(other)} replies`, 'They get to tell their side', past('opened', 'triage', 'assembling', 'awaiting_response')]
      : ['Your reply', 'Your side, in your words', past('opened', 'triage', 'assembling', 'awaiting_response')],
    ['Hearing both sides', 'An advocate argues for each of you', (e) => has('rider_advocate')(e) && has('driver_advocate')(e)],
    ['Decision', '', (_, s) => isFinal(s)],
  )
  return stages
}

export function Tracking({
  caseId,
  events,
  state,
  category,
  viewerSide,
  other,
  onDone,
}: {
  caseId: string
  events: TraceEvent[]
  state: CaseState | undefined
  category: Category | null
  viewerSide: 'complainer' | 'complainee'
  other: string
  onDone: () => void
}) {
  const safety = state === 'safety_bypassed' || category === 'safety_incident'
  const stages = stagesFor(viewerSide, other, category, safety)
  const at = state ? stages.findIndex(([, , done]) => !done(events, state)) : 0
  const done = at === -1 || (!!state && isFinal(state))
  const failed = errorOf(events)

  useEffect(() => {
    if (!done) return
    const t = setTimeout(onDone, 900)
    return () => clearTimeout(t)
  }, [done, onDone])

  return (
    <div className="app-view">
      <div className="app-head">
        <h2>{done ? 'Done' : 'In progress'}</h2>
        <p className="muted small">{category ? CAT[category] : 'Report'} · <span className="mono">{caseId}</span></p>
      </div>
      <div className="app-body">
        <div className="sheet">
          <ol className="tracker" aria-live="polite">
            {stages.map(([l, s], i) => {
              const cls = done || i < at ? 'done' : i === at ? 'now' : ''
              return (
                <li key={l} className={cls}>
                  <span className="dot">{cls === 'done' && <Icon name="check" size={15} stroke={2.6} />}</span>
                  <span className="lbl">{l}{s && <small>{s}</small>}</span>
                </li>
              )
            })}
          </ol>
        </div>
        {state === 'awaiting_response' && viewerSide === 'complainer' && (
          <Notice icon="clock">Nothing is decided before {first(other)} replies or 48 hours pass. Then the case is decided on the trip records.</Notice>
        )}
        {failed && (
          <Notice icon="alert" tone="bad">Something went wrong on our side while handling this report. Nothing has been decided.</Notice>
        )}
      </div>
    </div>
  )
}

export function Outcome({
  caseId,
  viewer,
  claimText,
  extra,
  footer,
}: {
  caseId: string
  viewer: Role
  claimText?: string | null
  extra?: ReactNode
  footer?: ReactNode
}) {
  const { data: o, error, reload } = useApi(`outcome:${caseId}:${viewer}`, () => api.outcome(caseId, viewer))
  if (error)
    return (
      <div className="app-view"><div className="app-body" style={{ paddingTop: 20 }}>
        <Notice icon="alert" tone="bad">We couldn’t load this outcome. <button className="btn-quiet" style={{ border: 0, background: 'none', padding: 0 }} onClick={reload}>Try again</button></Notice>
      </div></div>
    )
  if (!o) return <div className="app-view"><Loading /></div>
  const escalated = o.state === 'escalated'
  return (
    <div className="app-view">
      <div className="app-head"><p className="muted small">{o.state === 'safety_bypassed' ? 'Safety report' : 'Your report'} · <span className="mono">{caseId}</span></p></div>
      <div className="app-body">
        <ResultHero head={o.head} sub={o.sub} tone={o.tone} />
        <FactSheet title={o.state === 'safety_bypassed' ? undefined : escalated ? 'What we have so far' : 'What we found'} facts={o.facts} />
        {o.rule && (
          <div className="sheet"><h4>The rule we applied</h4><div className="rule-box"><span>{o.rule}</span></div></div>
        )}
        {o.viewer_side === 'complainer' && claimText && o.state !== 'safety_bypassed' && (
          <div className="sheet"><h4>What you told us</h4><p className="quote-box">“{claimText}”</p></div>
        )}
        {o.money && <Notice icon="receipt" tone="good">{o.money}</Notice>}
        {o.reviewed_by_person && <Notice icon="user">A person reviewed this decision before it was final.</Notice>}
        {extra}
      </div>
      {footer && <div className="app-footer">{footer}</div>}
    </div>
  )
}
