import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../lib/api'
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
    driver:
      'The rider spilled a drink all over the back seat and it needs professional cleaning. Photo attached.',
  },
  safety_incident: {
    rider: 'The driver was driving recklessly, ran a red light and shouted at me when I asked them to slow down. I felt unsafe.',
    driver: 'The rider became aggressive and threatened me during the trip.',
  },
}

export function FileClaim() {
  const { role, userId, tripId } = useParams() as { role: Role; userId: string; tripId: string }
  const navigate = useNavigate()
  const [trip, setTrip] = useState<Trip | null>(null)
  const [category, setCategory] = useState<Category>('route_deviation')
  const [text, setText] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.trips(userId).then(
      (trips) => {
        const found = trips.find((t) => t.id === tripId) ?? null
        setTrip(found)
        const hint = found?.scenario_hint as Category | undefined
        if (hint && hint in CATEGORY_LABEL) setCategory(hint)
      },
      (e: Error) => setError(e.message),
    )
  }, [userId, tripId])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    try {
      const evidence: EvidenceRef[] = []
      if (photo) {
        setBusy('Uploading photo…')
        evidence.push(await api.upload(photo, 'photo'))
      }
      setBusy('Filing claim…')
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

  return (
    <>
      <div className="page-head">
        <div>
          <Link to={`/${role}/${userId}`} className="small">
            ← Back to your panel
          </Link>
          <h1 style={{ marginTop: 6 }}>File a claim</h1>
          {trip && (
            <p>
              Trip on {when(trip.completed_at)} with {trip.other_party_name} · fare{' '}
              {money(trip.total_fare)}
            </p>
          )}
        </div>
      </div>

      <div className="grid-main">
        <form className="card stack" onSubmit={submit}>
          <label>
            What happened?
            <select value={category} onChange={(e) => setCategory(e.target.value as Category)}>
              {(Object.keys(CATEGORY_LABEL) as Category[]).map((c) => (
                <option key={c} value={c}>
                  {CATEGORY_LABEL[c]}
                </option>
              ))}
            </select>
          </label>

          <label>
            Describe it in your own words
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="What went wrong on this trip?"
              required
            />
          </label>
          <div>
            <button type="button" className="small" onClick={() => setText(EXAMPLES[category][role])}>
              Use example text
            </button>
          </div>

          <label>
            Photo {category === 'property_damage' ? '(required for property damage)' : '(optional)'}
            <input
              type="file"
              accept="image/*"
              onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
            />
          </label>

          {error && <p className="error-text">{error}</p>}
          <div className="row">
            <button className="primary" type="submit" disabled={Boolean(busy) || !text.trim()}>
              {busy ? (
                <>
                  <span className="spinner" /> {busy}
                </>
              ) : (
                'File claim'
              )}
            </button>
          </div>
        </form>

        <aside className="card small muted stack">
          <h3 style={{ color: 'var(--text)' }}>What happens next</h3>
          <div>
            1. <strong>Triage agent</strong> reads your description and confirms the category. Anything
            that sounds like a safety issue goes straight to a human reviewer.
          </div>
          <div>
            2. <strong>Prevention rules</strong> check the basics: a duplicate claim, the 30-day window,
            and a photo for damage claims.
          </div>
          <div>
            3. <strong>Evidence collection agent</strong> assembles the case file from trip records: GPS,
            route, fare, chat log, both parties' history.
          </div>
          <div>
            4. The other party is asked to respond. Then two advocates argue each side and a Judge
            decides. Confident, routine decisions are final; the rest go to a human.
          </div>
        </aside>
      </div>
    </>
  )
}
