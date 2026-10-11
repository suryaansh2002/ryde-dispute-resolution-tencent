import { useEffect, useState } from 'react'
import type { DragEvent, FormEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, samplePhotoUrl } from '../lib/api'
import { CATEGORY_LABEL, money, when } from '../lib/format'
import type { Category, EvidenceRef, Role, Trip } from '../types/api'

const EXAMPLES: Record<Category, Record<Role, string>> = {
  route_deviation: {
    rider:
      'The driver took a much longer route than the app showed and I was charged more for it. There was no traffic and I never asked for a detour.',
    driver:
      'The rider is disputing my route, but I followed the navigation and the detour was needed because of a road closure.',
  },
  no_show_charge: {
    rider:
      'The driver never came to the pickup point. I waited outside for ten minutes and was still charged a no-show fee.',
    driver:
      'I arrived at the pickup point and waited well past the required time, messaged the rider, and they never came out.',
  },
  property_damage: {
    rider: 'I am being charged a cleaning fee for a mess I did not make.',
    driver: 'The rider spilled a drink all over the back seat and it needs professional cleaning. Photo attached.',
  },
  safety_incident: {
    rider:
      'The driver was driving recklessly, ran a red light and shouted at me when I asked them to slow down. I felt unsafe.',
    driver: 'The rider became aggressive and threatened me during the trip.',
  },
}

const CATEGORY_HINT: Record<Category, string> = {
  route_deviation: 'Longer route, higher fare',
  no_show_charge: 'Charged for not turning up',
  property_damage: 'Cleaning or damage fee',
  safety_incident: 'You felt unsafe',
}

const WE_CHECK: Record<Category, string[]> = {
  route_deviation: [
    'The planned route against the route actually driven, to the metre',
    'Recorded traffic incidents near the route at the time',
    'The chat log, in case a detour was asked for',
    'The fare breakdown. Any refund comes from Ryde’s formula, not the AI',
  ],
  no_show_charge: [
    'Whether the driver’s GPS ever came within 100 m of the pickup',
    'How long the driver waited, against the grace period',
    'Messages between you before the cancellation',
    'The $4.50 fee as charged',
  ],
  property_damage: [
    'Your photo: hashed so it can’t change, then graded by Image Analysis (spill, mud, vomit…)',
    'The fee tier follows what the photo shows, not what the report says',
    'Ryde’s fixed cleaning-fee tiers: $40, $120 or $200',
    'The chat log and both parties’ dispute history',
  ],
  safety_incident: [
    'Nothing automated. A safety specialist reads this directly',
    'No AI agent argues or decides a safety report',
  ],
}

type SampleTier = 'none' | 'minor' | 'moderate' | 'severe'

const SAMPLE_LABEL: Record<SampleTier, string> = {
  minor: 'Coffee spill',
  moderate: 'Mud',
  severe: 'Vomit',
  none: 'Clean seat',
}

/** A synthetic rear-seat photo from the backend, real enough for Image Analysis to grade. */
async function samplePhoto(tier: SampleTier): Promise<File> {
  const res = await fetch(samplePhotoUrl(tier, Math.floor(Math.random() * 1000)))
  if (!res.ok) throw new Error(`sample photo: ${res.status}`)
  return new File([await res.blob()], `rear-seat-${tier}.jpg`, { type: 'image/jpeg' })
}

export function FileClaim() {
  const { role, userId, tripId } = useParams() as { role: Role; userId: string; tripId: string }
  const [params] = useSearchParams()
  const demo = params.get('demo') === '1'
  const navigate = useNavigate()
  const [trip, setTrip] = useState<Trip | null>(null)
  const [category, setCategory] = useState<Category>((params.get('category') as Category) ?? 'route_deviation')
  const [text, setText] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [drag, setDrag] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.trips(userId).then(
      (trips) => {
        const found = trips.find((t) => t.id === tripId) ?? null
        setTrip(found)
        const hint = found?.scenario_hint as Category | undefined
        if (!params.get('category') && hint && hint in CATEGORY_LABEL) setCategory(hint)
      },
      (e: Error) => setError(e.message),
    )
  }, [userId, tripId, params])

  // Demo mode pre-fills the claim (and a sample photo for damage) so a run is one click.
  useEffect(() => {
    if (!demo) return
    setText(EXAMPLES[category][role])
    if (category === 'property_damage') samplePhoto('minor').then(setPhoto, () => setPhoto(null))
  }, [demo, category, role])

  useEffect(() => {
    if (!photo) {
      setPreview(null)
      return
    }
    const url = URL.createObjectURL(photo)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [photo])

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDrag(false)
    const f = e.dataTransfer.files?.[0]
    if (f && f.type.startsWith('image/')) setPhoto(f)
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    try {
      const evidence: EvidenceRef[] = []
      if (photo) {
        setBusy('Uploading photo…')
        evidence.push(await api.upload(photo, 'photo'))
      }
      setBusy('Filing…')
      const accepted = await api.fileClaim({
        trip_id: tripId,
        complainer_id: userId,
        category,
        claim_text: text.trim(),
        evidence,
      })
      navigate(`/${role}/${userId}/case/${accepted.case_id}`)
    } catch (err) {
      setError((err as Error).message)
      setBusy(null)
    }
  }

  const needsPhoto = category === 'property_damage'

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="page-head" style={{ marginBottom: 0 }}>
        <div className="stack" style={{ gap: 6 }}>
          <Link to={`/${role}/${userId}`} className="small muted">
            ← Your trips
          </Link>
          <h1>Report a problem with this trip</h1>
          {trip && (
            <p className="muted">
              {when(trip.completed_at)} with {trip.other_party_name} · <span className="mono">{money(trip.total_fare)}</span>
            </p>
          )}
        </div>
        {demo && <span className="badge tone-live">Demo: claim pre-filled, edit anything</span>}
      </div>

      <div className="split">
        <form className="panel panel-pad stack" style={{ gap: 18 }} onSubmit={submit}>
          <div className="stack" style={{ gap: 8 }}>
            <span className="eyebrow">1 · What happened?</span>
            <div className="tiles" role="radiogroup">
              {(Object.keys(CATEGORY_LABEL) as Category[]).map((c) => (
                <button
                  key={c}
                  type="button"
                  role="radio"
                  aria-checked={category === c}
                  className={`tile${category === c ? ' on' : ''}`}
                  onClick={() => setCategory(c)}
                >
                  <strong>{CATEGORY_LABEL[c]}</strong>
                  <span className="tiny muted">{CATEGORY_HINT[c]}</span>
                </button>
              ))}
            </div>
          </div>

          <label className="field">
            <span className="eyebrow">2 · In your own words</span>
            <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="What went wrong on this trip?" required />
            <span className="tiny faint" style={{ fontWeight: 400 }}>
              Your words go to the agents arguing the case, never to the Judge, who rules on the evidence alone.{' '}
              {!demo && (
                <button type="button" className="btn-ghost btn-sm" style={{ padding: '0 4px' }} onClick={() => setText(EXAMPLES[category][role])}>
                  Use example text
                </button>
              )}
            </span>
          </label>

          {category !== 'safety_incident' && (
            <div className="stack" style={{ gap: 8 }}>
              <span className="eyebrow">3 · Photo {needsPhoto ? '(required)' : '(optional)'}</span>
              <label
                className={`dropzone${drag ? ' drag' : ''}`}
                onDragOver={(e) => {
                  e.preventDefault()
                  setDrag(true)
                }}
                onDragLeave={() => setDrag(false)}
                onDrop={onDrop}
              >
                {preview ? (
                  <img src={preview} alt="Attached photo" style={{ width: 96, height: 64, objectFit: 'cover', borderRadius: 6 }} />
                ) : (
                  <span className="avatar ink" aria-hidden>
                    ＋
                  </span>
                )}
                <span className="grow small">
                  {photo ? (
                    <>
                      <strong>{photo.name}</strong> <span className="faint">· {Math.round(photo.size / 1024)} KB</span>
                    </>
                  ) : (
                    <>Drop a photo here or click to choose</>
                  )}
                  <span className="tiny faint" style={{ display: 'block' }}>
                    Stored privately and fingerprinted (SHA-256) so it can’t be swapped later.
                  </span>
                </span>
                <input type="file" accept="image/*" style={{ display: 'none' }} onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
              </label>
              <div className="row">
                {photo && (
                  <button type="button" className="btn-ghost btn-sm" onClick={() => setPhoto(null)}>
                    Remove photo
                  </button>
                )}
                {needsPhoto && (
                  <>
                    <span className="tiny faint">Demo sample photo:</span>
                    <div className="segmented">
                      {(Object.keys(SAMPLE_LABEL) as SampleTier[]).map((t) => (
                        <button
                          key={t}
                          type="button"
                          className={`btn-sm ${photo?.name === `rear-seat-${t}.jpg` ? 'on' : ''}`}
                          onClick={() => samplePhoto(t).then(setPhoto, (e: Error) => setError(e.message))}
                        >
                          {SAMPLE_LABEL[t]}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
              {needsPhoto && !photo && (
                <p className="tiny" style={{ color: 'var(--warn)' }}>
                  Without a photo, a damage claim is declined for insufficient evidence. That isn’t a ruling: you could refile.
                </p>
              )}
            </div>
          )}

          {error && <p className="error-text">{error}</p>}
          <div className="row">
            <button className="btn-primary" type="submit" disabled={Boolean(busy) || !text.trim()}>
              {busy ? (
                <>
                  <span className="spinner" /> {busy}
                </>
              ) : (
                'Submit report'
              )}
            </button>
            <span className="tiny faint">You’ll watch it being checked straight away.</span>
          </div>
        </form>

        <aside className="stack">
          <section className="panel panel-pad stack" style={{ gap: 10 }}>
            <span className="eyebrow">What we check automatically</span>
            <ul className="principles">
              {WE_CHECK[category].map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          </section>
          <section className="panel panel-pad stack" style={{ gap: 10 }}>
            <span className="eyebrow">What happens next</span>
            <ol className="findings">
              <li>
                <div className="small">
                  <strong>Checks.</strong> An agent reads your report; plain-code rules check the basics (duplicate, 30-day
                  window, a photo where needed).
                </div>
              </li>
              <li>
                <div className="small">
                  <strong>The other side responds.</strong> {trip?.other_party_name ?? 'They'} gets to tell their side
                  first.
                </div>
              </li>
              <li>
                <div className="small">
                  <strong>A hearing.</strong> One advocate for each of you argues from the same trip record; a Judge rules.
                </div>
              </li>
              <li>
                <div className="small">
                  <strong>A person if needed.</strong> Low confidence, repeat filings, large fees and safety always go to a
                  human.
                </div>
              </li>
            </ol>
          </section>
        </aside>
      </div>
    </div>
  )
}
