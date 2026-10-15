import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import type { CaseSummary, CaseView, Category, EvidenceRef, Role, Trip } from '../types/api'
import { api, ApiError, samplePhotoUrl } from '../lib/api'
import { CAT, clock, day, first, initials, isFinal, money, statusPill } from '../lib/format'
import { useEvidence, useLiveCase } from '../lib/live'
import { invalidate, useApi } from '../lib/useApi'
import { DemoPanel } from '../components/DemoPanel'
import { Receipt } from '../components/evidence'
import { Icon } from '../components/Icon'
import {
  ChatIntake, EXAMPLE_REPLY, FeeTable, KIND_CATEGORY, Outcome, RULE, Tracking,
  type IntakeResult, type IssueKind,
} from '../components/party'
import { TripMap, geoFromEvidence, geoFromTrip } from '../components/TripMap'
import { Back, ErrorNote, Loading, Notice, Phone } from '../components/ui'

/* The rider and driver apps: a phone running on the live API, with the narration on the
   left and the hearing behind it on the right. */

interface Scenario {
  key: string
  title: string
  note: string
  /** File a new report of this kind on a fresh trip. */
  category?: Category
  /** Driver only: answer a report someone filed against you. */
  respond?: boolean
}

const SCENARIOS: Record<Role, Scenario[]> = {
  rider: [
    { key: 'route', category: 'route_deviation', title: 'The long way round', note: 'A trip whose GPS record shows a detour. Report the route.' },
    { key: 'noshow', category: 'no_show_charge', title: 'Charged for a no-show', note: 'You were charged $4.50. Report the fee.' },
    { key: 'safety', category: 'safety_incident', title: 'Something felt unsafe', note: 'Goes straight to a person on the safety team.' },
  ],
  driver: [
    { key: 'respond', respond: true, title: 'A rider reported your trip', note: 'Reply, then see the outcome from your side.' },
    { key: 'damage', category: 'property_damage', title: 'Report a mess in your car', note: 'A photo check sets the fee tier. $120 or more goes to a person.' },
    { key: 'nophoto', category: 'property_damage', title: 'A cleaning fee without a photo', note: 'Declined, not denied. Add a photo and send again.' },
    { key: 'noshow', category: 'no_show_charge', title: 'The rider didn’t show up', note: 'Your GPS near the pickup decides it.' },
  ],
}

type Screen = 'inbox' | 'trips' | 'trip' | 'chat' | 'review' | 'claim' | 'reply' | 'tracking' | 'outcome'

const CAPTIONS: Record<Role, Partial<Record<Screen, [string, string]>>> = {
  rider: {
    trips: ['Start from the trip', 'Disputes start from a real trip, so the rider never types a trip ID, fare or driver name.'],
    trip: ['The trip, as a receipt', 'The map is drawn from the trip’s own GPS record: the fastest route dashed, the route driven solid.'],
    chat: ['Say it in your own words', 'A chat takes the report. The triage agent reads these words and the chat answers with what it heard: the kind of dispute, or a safety report that goes straight to a person. Quick replies are there for anyone who’d rather tap.'],
    review: ['The rule, before sending', 'The policy is shown up front in plain words, along with what happens next.'],
    tracking: ['Real progress', 'The rider sees plain stages. The panel on the right shows the hearing behind them, step by step, as it runs.'],
    outcome: ['A fair outcome', 'What we found, the rule applied, and where the money goes. Same facts the driver sees, from their side.'],
  },
  driver: {
    inbox: ['Told, not surprised', 'The driver hears about the report straight away, with the trip it’s about.'],
    claim: ['Their side, in full', 'The driver sees exactly what the rider said, and has time to answer before anything is decided.'],
    reply: ['A real chance to reply', 'The reply goes to the advocate arguing the driver’s side. The Judge never sees either party’s words.'],
    trips: ['Drivers file too', 'A driver reports a problem from the trip, exactly like a rider does.'],
    trip: ['The trip, as a receipt', 'Same trip record the rider sees.'],
    chat: ['Say it, add a photo', 'The chat asks for what this kind of claim needs: here, a photo. Without one, the claim is declined, not denied.'],
    review: ['The fee table, before sending', 'Ryde’s published cleaning-fee tiers, and the rule that the photo sets the tier.'],
    tracking: ['The same hearing', 'Both sides are argued from identical trip records. The panel on the right shows each step as it happens.'],
    outcome: ['The same facts', 'The outcome uses the same facts and rule the other side sees, told from the driver’s side.'],
  },
}

interface Persona {
  id: string
  name: string
}

export function PartyApp({ role }: { role: Role }) {
  const other: Role = role === 'rider' ? 'driver' : 'rider'
  const [params, setParams] = useSearchParams()
  const deepCase = params.get('case')
  const [scenario, setScenario] = useState<Scenario | null>(() =>
    deepCase ? null : SCENARIOS[role].find((s) => s.key === params.get('start')) ?? SCENARIOS[role][0],
  )
  const [round, setRound] = useState(0)
  const [persona, setPersona] = useState<Persona | null>(null)
  const [featuredTrip, setFeaturedTrip] = useState<string | null>(null)
  const [tripId, setTripId] = useState<string | null>(null)
  const [inbox, setInbox] = useState<CaseSummary[] | null>(null)
  const [screen, setScreen] = useState<Screen>(role === 'driver' ? 'inbox' : 'trips')
  const [caseId, setCaseId] = useState<string | null>(deepCase)
  const [intake, setIntake] = useState<IntakeResult | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [busy, setBusy] = useState(false)
  const [reply, setReply] = useState('')
  // Resending a declined cleaning fee: same trip, this time with the sample photo.
  const [withPhoto, setWithPhoto] = useState(false)

  const live = useLiveCase(caseId)
  const view = live.view

  // Load the scenario: a persona and the trip (or the report) it's about.
  useEffect(() => {
    if (!scenario) return
    let on = true
    setError(null)
    setPersona(null)
    setCaseId(null)
    setTripId(null)
    setFeaturedTrip(null)
    setInbox(null)
    setIntake(null)
    setWithPhoto(false)
    ;(async () => {
      try {
        if (scenario.respond) {
          const people = await api.personas('driver', 60)
          const waiting = people.find((p) => p.awaiting_my_response > 0)
          if (!waiting) {
            if (on) {
              setPersona(people[0] ? { id: people[0].id, name: people[0].display_name } : null)
              setInbox([])
              setScreen('inbox')
            }
            return
          }
          const cases = await api.userCases(waiting.id)
          if (!on) return
          setPersona({ id: waiting.id, name: waiting.display_name })
          setInbox(cases.filter((c) => c.needs_my_response))
          setScreen('inbox')
        } else if (scenario.category) {
          const s = await api.scenario(scenario.category, role)
          if (!on) return
          setPersona({ id: s.user_id, name: s.display_name })
          setFeaturedTrip(s.trip_id)
          setScreen('trips')
        }
      } catch (e) {
        if (on) setError(e as Error)
      }
    })()
    return () => {
      on = false
    }
  }, [scenario, round, role])

  // A deep link (/driver?case=CASE-0153) opens that case as the party on this side of it.
  useEffect(() => {
    if (!deepCase || !view || view.id !== deepCase) return
    const mine = view.complainer_role === role
    setPersona(mine ? { id: view.complainer_id, name: view.complainer_name } : { id: view.complainee_id, name: view.complainee_name })
    setScreen(
      view.state === 'awaiting_response' && !mine ? 'claim' : isFinal(view.state) ? 'outcome' : 'tracking',
    )
    setParams({}, { replace: true })
    // only when the deep-linked case first loads
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deepCase, view?.id])

  const viewerSide: 'complainer' | 'complainee' =
    view && persona && view.complainee_id === persona.id ? 'complainee' : 'complainer'
  const otherName = view ? (viewerSide === 'complainer' ? view.complainee_name : view.complainer_name) : ''
  const category: Category | null = view?.category ?? scenario?.category ?? null

  const openCase = (id: string, state: CaseView['state'] | null) => {
    setCaseId(id)
    setScreen(state && isFinal(state) ? 'outcome' : 'tracking')
  }

  const send = async () => {
    if (!intake || !persona || !tripId) return
    setBusy(true)
    setError(null)
    try {
      const evidence: EvidenceRef[] = []
      if (intake.photo) {
        const file = new File([intake.photo], 'photo.jpg', { type: intake.photo.type || 'image/jpeg' })
        evidence.push(await api.upload(file, 'photo'))
      }
      const res = await api.fileClaim({
        trip_id: tripId,
        complainer_id: persona.id,
        category: KIND_CATEGORY[intake.kind],
        claim_text: intake.text,
        evidence,
      })
      invalidate(`trips:${persona.id}`)
      setCaseId(res.case_id)
      setScreen('tracking')
    } catch (e) {
      setError(e as Error)
    } finally {
      setBusy(false)
    }
  }

  const sendReply = async () => {
    if (!caseId || !persona) return
    setBusy(true)
    setError(null)
    try {
      await api.respond(caseId, persona.id, reply)
      setScreen('tracking')
    } catch (e) {
      setError(e as Error)
    } finally {
      setBusy(false)
    }
  }

  const decideNow = async () => {
    if (!caseId) return
    try {
      await api.adjudicateNow(caseId)
    } catch (e) {
      setError(e as Error)
    }
  }

  const restart = () => {
    if (!scenario) setScenario(SCENARIOS[role][0])
    else setRound((r) => r + 1)
  }

  const onTrackingDone = useCallback(() => setScreen('outcome'), [])
  const cap = CAPTIONS[role][screen]
  const tone = role

  const waitingFor =
    live.state === 'awaiting_response' && view ? view.complainee_name : null
  const demoActions =
    caseId && live.state === 'awaiting_response' && viewerSide === 'complainer' && view ? (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-start' }}>
        <Link className="btn btn-primary btn-sm" to={`/${other}?case=${caseId}`}>
          <Icon name={other === 'driver' ? 'car' : 'phone'} size={14} />
          Answer as {first(view.complainee_name)}
        </Link>
        <button className="btn-quiet small" style={{ border: 0, background: 'none' }} onClick={decideNow}>
          Or skip the reply and decide on the records
        </button>
      </div>
    ) : null

  return (
    <div className="page">
      <div className="stage three">
        <div className="narration">
          <div className="persona">
            <span className={`avatar ${tone}`}>{persona ? initials(persona.name) : ''}</span>
            <div>
              <h1>{persona?.name ?? (error ? 'No persona' : 'Loading…')}</h1>
              <span className={`party ${tone}`}><i />{role === 'rider' ? 'Rider' : 'Driver'}</span>
            </div>
          </div>
          <div className="scenarios" role="group" aria-label="Scenario">
            <h2>Scenario</h2>
            {SCENARIOS[role].map((s) => (
              <button
                key={s.key} className="scenario" aria-pressed={scenario?.key === s.key}
                onClick={() => { setScenario(s); setRound((r) => r + 1) }}
              >
                <span className="radio" />
                <span><strong>{s.title}</strong><span>{s.note}</span></span>
              </button>
            ))}
          </div>
          {cap && (
            <div className="caption" aria-live="polite">
              <h3>{cap[0]}</h3>
              <p>{cap[1]}</p>
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn btn-secondary btn-sm" onClick={restart}><Icon name="replay" size={14} />Start over</button>
          </div>
          <p className="tiny muted">Each report runs the real pipeline: real model calls, real rules, real records.</p>
        </div>

        <div className="phone-wrap">
          <Phone>
            {error && screen !== 'review' && screen !== 'reply' && (
              <div className="app-view"><div className="app-body" style={{ paddingTop: 20 }}>
                <ErrorNote error={error} retry={restart} />
                {error instanceof ApiError && error.status === 404 && (
                  <p className="small muted" style={{ padding: '0 6px' }}>
                    No unused demo trip of this kind is left in the 30-day window. Run <span className="mono">scripts.shift_dates</span> or regenerate the demo data.
                  </p>
                )}
              </div></div>
            )}
            {!error && !persona && screen !== 'outcome' && screen !== 'tracking' && <div className="app-view"><Loading /></div>}

            {!error && persona && screen === 'inbox' && (
              <Inbox
                cases={inbox} name={persona.name} role={role}
                onOpen={(c) => { setCaseId(c.id); setScreen(c.needs_my_response ? 'claim' : isFinal(c.state) ? 'outcome' : 'tracking') }}
              />
            )}

            {!error && persona && screen === 'trips' && (
              <Trips
                role={role} personaId={persona.id} name={persona.name} featured={featuredTrip}
                onTrip={(id) => { setTripId(id); setScreen('trip') }}
                onCase={openCase}
              />
            )}

            {screen === 'trip' && tripId && (
              <TripScreen
                tripId={tripId} role={role}
                onBack={() => setScreen('trips')}
                onReport={() => setScreen('chat')}
                onCase={openCase}
              />
            )}

            {screen === 'chat' && tripId && persona && (
              <ChatForTrip
                key={`${tripId}${round}`} tripId={tripId} role={role} me={persona.name}
                sample={withPhoto || scenario?.key !== 'nophoto'} category={view?.category ?? scenario?.category ?? null}
                onReview={(r) => { setIntake(r); setScreen('review') }}
              />
            )}

            {screen === 'review' && intake && (
              <Review
                role={role} intake={intake} busy={busy} error={error}
                onBack={() => setScreen('chat')} onSend={send}
              />
            )}

            {screen === 'claim' && caseId && (
              <ClaimScreen
                caseId={caseId} view={view}
                onBack={() => setScreen('inbox')}
                onReply={() => { setReply(EXAMPLE_REPLY[view?.category ?? 'route_deviation'] ?? ''); setScreen('reply') }}
              />
            )}

            {screen === 'reply' && (
              <div className="app-view">
                <div className="app-head"><Back onClick={() => setScreen('claim')} /><h2>Your side</h2></div>
                <div className="app-body">
                  <div>
                    <label className="field-label" htmlFor="reply">What happened, in your words</label>
                    <textarea id="reply" className="input" value={reply} onChange={(e) => setReply(e.target.value)} />
                    <p className="tiny muted" style={{ padding: '6px 6px 0' }}>Example reply for the demo. Edit it freely.</p>
                  </div>
                  <div className="sheet"><ul className="facts"><li><Icon name="scale" size={18} /><span>An advocate argues your side using your reply and the trip records.</span></li></ul></div>
                  {error && <ErrorNote error={error} />}
                </div>
                <div className="app-footer">
                  <button className="btn btn-primary btn-block" disabled={!reply.trim() || busy} onClick={sendReply}>
                    <Icon name="send" size={17} />{busy ? 'Sending…' : 'Send reply'}
                  </button>
                </div>
              </div>
            )}

            {screen === 'tracking' && caseId && (
              <Tracking
                caseId={caseId} events={live.events} state={live.state} category={category}
                viewerSide={viewerSide} other={otherName || '…'} onDone={onTrackingDone}
              />
            )}

            {screen === 'outcome' && caseId && live.state && isFinal(live.state) && (
              <Outcome
                key={`${caseId}:${live.state}`}
                caseId={caseId} viewer={role} claimText={view?.claim_text}
                footer={
                  <OutcomeFooter
                    canRefile={live.state === 'declined_insufficient_evidence' && category === 'property_damage' && viewerSide === 'complainer'}
                    onRefile={() => { setTripId(view?.trip_id ?? tripId); setCaseId(null); setWithPhoto(true); setScreen('chat') }}
                    onDone={() => { setCaseId(null); setScreen(role === 'driver' && scenario?.respond ? 'inbox' : 'trips') }}
                  />
                }
              />
            )}
            {screen === 'outcome' && caseId && !(live.state && isFinal(live.state)) && <div className="app-view"><Loading /></div>}
          </Phone>
        </div>

        <DemoPanel caseId={caseId} live={live} category={category} waitingFor={waitingFor} actions={demoActions} />
      </div>
    </div>
  )
}

function OutcomeFooter({ canRefile, onRefile, onDone }: { canRefile: boolean; onRefile: () => void; onDone: () => void }) {
  return canRefile ? (
    <>
      <button className="btn btn-primary btn-block" onClick={onRefile}><Icon name="photoAdd" size={17} />Add a photo and send again</button>
      <button className="btn btn-secondary btn-block" onClick={onDone}>Done</button>
    </>
  ) : (
    <button className="btn btn-secondary btn-block" onClick={onDone}>Done</button>
  )
}

function AppUser({ name, role }: { name: string; role: Role }) {
  return (
    <div className="app-user">
      <span className={`avatar ${role}`}>{initials(name)}</span>
      <span>{name}</span>
    </div>
  )
}

function Inbox({ cases, name, role, onOpen }: {
  cases: CaseSummary[] | null
  name: string
  role: Role
  onOpen: (c: CaseSummary) => void
}) {
  if (!cases) return <div className="app-view"><Loading /></div>
  return (
    <div className="app-view">
      <div className="app-head"><AppUser name={name} role={role} /><h2>Inbox</h2></div>
      <div className="app-body">
        {cases.length === 0 ? (
          <div className="sheet sheet-pad">
            <p style={{ fontWeight: 600 }}>Nothing to answer</p>
            <p className="small muted" style={{ marginTop: 4 }}>
              No report is waiting for a driver’s reply. File one from the <Link to="/rider">rider app</Link>, then answer it here.
            </p>
          </div>
        ) : (
          <div className="sheet">
            {cases.map((c) => (
              <button key={c.id} className="row" onClick={() => onOpen(c)}>
                <span className="avatar rider" style={{ width: 34, height: 34, fontSize: 12 }}>{initials(c.other_party_name)}</span>
                <div className="grow">
                  <div className="title">{first(c.other_party_name)} reported a trip</div>
                  <div className="sub">{c.category ? CAT[c.category] : 'Report'} · reply within 48 hours</div>
                </div>
                <span className="pill warn">New</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function Trips({
  role, personaId, name, featured, onTrip, onCase,
}: {
  role: Role
  personaId: string
  name: string
  featured: string | null
  onTrip: (id: string) => void
  onCase: (id: string, state: CaseView['state'] | null) => void
}) {
  const { data: trips, error, reload } = useApi(`trips:${personaId}`, () => api.trips(personaId))
  const { data: top } = useApi(featured ? `trip:${featured}` : null, () => api.trip(featured!))
  if (error) return <div className="app-view"><div className="app-body" style={{ paddingTop: 20 }}><ErrorNote error={error} retry={reload} /></div></div>
  if (!trips) return <div className="app-view"><Loading /></div>
  const featuredTrip = trips.find((t) => t.id === featured)
  const rest = trips.filter((t) => t.id !== featured).slice(0, 5)
  const open = (t: Trip) => (t.case_id ? onCase(t.case_id, t.case_state) : onTrip(t.id))
  return (
    <div className="app-view">
      <div className="app-head"><AppUser name={name} role={role} /><h2>{role === 'rider' ? 'Activity' : 'Trips'}</h2></div>
      <div className="app-body">
        {featuredTrip && (
          <div className="sheet">
            {top && <div style={{ borderBottom: '1px solid var(--hair)' }}><TripMap geo={geoFromTrip(top)} id={`t${top.id}`} legend={false} /></div>}
            <TripRow t={featuredTrip} onClick={() => open(featuredTrip)} />
          </div>
        )}
        {rest.length > 0 && (
          <>
            <p className="field-label" style={{ paddingTop: 6 }}>Earlier</p>
            <div className="sheet">{rest.map((t) => <TripRow key={t.id} t={t} onClick={() => open(t)} />)}</div>
          </>
        )}
        <p className="tiny muted" style={{ padding: '0 6px' }}>Synthetic demo trips from the RydeResolve dataset.</p>
      </div>
    </div>
  )
}

function TripRow({ t, onClick }: { t: Trip; onClick: () => void }) {
  const pill = t.case_state ? statusPill(t.case_state) : null
  return (
    <button className="row" onClick={onClick}>
      <div className="grow">
        <div className="title">{day(t.completed_at)} · {clock(t.scheduled_at)}</div>
        <div className="sub">With {t.other_party_name} · {money(t.total_fare)}</div>
      </div>
      {pill ? <span className={`pill ${pill[0]}`}>{pill[1]}</span> : <Icon name="right" size={18} style={{ color: 'var(--ink-4)' }} />}
    </button>
  )
}

function TripScreen({
  tripId, role, onBack, onReport, onCase,
}: {
  tripId: string
  role: Role
  onBack: () => void
  onReport: () => void
  onCase: (id: string, state: CaseView['state'] | null) => void
}) {
  const { data: trip, error, reload } = useApi(`trip:${tripId}`, () => api.trip(tripId))
  if (error) return <div className="app-view"><div className="app-body" style={{ paddingTop: 20 }}><ErrorNote error={error} retry={reload} /></div></div>
  if (!trip) return <div className="app-view"><Loading /></div>
  const them = role === 'rider' ? trip.driver : trip.rider
  return (
    <div className="app-view">
      <div className="app-head"><Back onClick={onBack} label={role === 'rider' ? 'Activity' : 'Trips'} /><h2>{day(trip.completed_at)} trip</h2></div>
      <div className="app-body">
        <div className="sheet"><TripMap geo={geoFromTrip(trip)} id={`trip${trip.id}`} /></div>
        <div className="sheet">
          <div className="row">
            <span className={`avatar ${role === 'rider' ? 'driver' : 'rider'}`} style={{ width: 34, height: 34, fontSize: 12 }}>{initials(them.name)}</span>
            <div className="grow"><div className="title">{them.name}</div><div className="sub">Your {role === 'rider' ? 'driver' : 'rider'}</div></div>
          </div>
          {trip.payment && <div className="sheet-pad" style={{ borderTop: '1px solid var(--hair)' }}><Receipt data={trip.payment} /></div>}
        </div>
      </div>
      <div className="app-footer">
        {trip.case_id && trip.case_state !== 'declined_insufficient_evidence' ? (
          <button className="btn btn-secondary btn-block" onClick={() => onCase(trip.case_id!, trip.case_state)}>View your report</button>
        ) : (
          <button className="btn btn-primary btn-block" onClick={onReport}>Report a problem</button>
        )}
      </div>
    </div>
  )
}

function ChatForTrip({
  tripId, role, me, sample, category, onReview,
}: {
  tripId: string
  role: Role
  me: string
  /** Offer the generated sample photo (the demo's "camera"). */
  sample: boolean
  category: Category | null
  onReview: (r: IntakeResult) => void
}) {
  const { data: trip } = useApi(`trip:${tripId}`, () => api.trip(tripId))
  // A different generated photo each report, fixed for this chat.
  const [seed] = useState(() => Math.floor(Math.random() * 50))
  if (!trip) return <div className="app-view"><Loading /></div>
  const them = role === 'rider' ? trip.driver : trip.rider
  const suggested = (Object.entries(KIND_CATEGORY).find(([, c]) => c === category)?.[0] ?? null) as IssueKind | null
  return (
    <ChatIntake
      tripId={tripId} who={role} me={me} other={them.name} tripDate={trip.completed_at} fare={trip.payment?.total_fare ?? null}
      suggested={suggested} samplePhoto={sample ? samplePhotoUrl('moderate', seed) : null}
      onReview={onReview}
    />
  )
}

function Review({
  role, intake, busy, error, onBack, onSend,
}: {
  role: Role
  intake: IntakeResult
  busy: boolean
  error: Error | null
  onBack: () => void
  onSend: () => void
}) {
  const safety = intake.kind === 'safety'
  const category = KIND_CATEGORY[intake.kind]
  const [photoUrl] = useState(() => (intake.photo ? URL.createObjectURL(intake.photo) : null))
  const other = role === 'rider' ? 'the driver' : 'the rider'
  return (
    <div className="app-view">
      <div className="app-head"><Back onClick={onBack} /><h2>{safety ? 'Send to our safety team' : 'Before you send'}</h2></div>
      <div className="app-body">
        {safety ? (
          <Notice icon="shield" tone="bad">
            <strong>A person handles this</strong>
            <br />
            A safety specialist reads your report and contacts you. If you’re in danger right now, call 999.
          </Notice>
        ) : (
          <>
            <div className="sheet"><h4>Your report</h4><p className="quote-box">“{intake.text}”</p></div>
            {category === 'property_damage' ? (
              <>
                {photoUrl ? (
                  <div className="sheet"><div className="photo"><img src={photoUrl} alt="Your photo" /></div></div>
                ) : (
                  <Notice icon="camera">No photo attached. Cleaning fees need one, so this report will be declined. You can add a photo and send it again.</Notice>
                )}
                <FeeTable />
              </>
            ) : (
              <div className="sheet"><h4>How this is decided</h4><div className="rule-box"><span>{RULE[category]}</span><span className="tiny muted">RydeResolve policy for this kind of dispute.</span></div></div>
            )}
            <div className="sheet">
              <h4>What happens next</h4>
              <ul className="facts">
                {category === 'property_damage' && <li><Icon name="camera" size={18} /><span>A photo check reads what the photo shows.</span></li>}
                <li><Icon name="msg" size={18} /><span>{other[0].toUpperCase() + other.slice(1)} gets the chance to reply.</span></li>
                <li><Icon name="scale" size={18} /><span>Both sides are argued from the same trip records.</span></li>
                <li>
                  <Icon name={category === 'property_damage' ? 'user' : 'clock'} size={18} />
                  <span>{category === 'property_damage' ? 'Fees of $120 or more always get a person’s review before anyone is charged.' : 'A decision usually follows within a minute of that. Anything unclear goes to a person.'}</span>
                </li>
              </ul>
            </div>
          </>
        )}
        {error && <ErrorNote error={error} />}
      </div>
      <div className="app-footer">
        <button className="btn btn-primary btn-block" disabled={busy} onClick={onSend}>
          <Icon name="send" size={17} />{busy ? 'Sending…' : safety ? 'Send to the safety team' : 'Send report'}
        </button>
      </div>
    </div>
  )
}

function ClaimScreen({
  caseId, view, onBack, onReply,
}: {
  caseId: string
  view: CaseView | undefined
  onBack: () => void
  onReply: () => void
}) {
  const { data: ev } = useEvidence(view?.has_case_file === false ? null : caseId, 'party')
  if (!view) return <div className="app-view"><Loading /></div>
  const canReply = view.state === 'awaiting_response'
  return (
    <div className="app-view">
      <div className="app-head">
        <Back onClick={onBack} label="Inbox" />
        <h2>{view.category ? CAT[view.category] : 'Report'}</h2>
        <p className="muted small">{day(view.trip?.completed_at)} trip with {view.complainer_name}</p>
      </div>
      <div className="app-body">
        <div className="sheet"><h4>What {first(view.complainer_name)} said</h4><p className="quote-box">“{view.claim_text}”</p></div>
        {ev && Object.keys(ev).length > 0 && <div className="sheet"><TripMap geo={geoFromEvidence(ev)} id={`c${caseId}`} /></div>}
        <Notice icon="clock">Nothing is decided before you reply or 48 hours pass. Then the case is decided on the trip records.</Notice>
      </div>
      <div className="app-footer">
        <button className="btn btn-primary btn-block" disabled={!canReply} onClick={onReply}>{canReply ? 'Reply' : 'Already answered'}</button>
      </div>
    </div>
  )
}
