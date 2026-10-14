import type { EvidenceIndex, TripDetail } from '../types/api'

/* A schematic map drawn from the trip's own coordinates: the fastest route dashed, the
   route driven solid, recorded roadworks, and for a no-show the driver's GPS fixes
   against the pickup's arrival radius. No tiles, so it never fails to load. */

type LngLat = [number, number]

export interface Geo {
  optimal: LngLat[]
  actual: LngLat[]
  gps: { lat: number; lng: number }[]
  prox: {
    pickup: { lat: number; lng: number }
    closest_approach_m: number
    arrival_radius_m: number
    reached_pickup: boolean
  } | null
  traffic: { k: string; lat: number; lng: number; type?: string }[]
}

export function geoFromEvidence(ev: EvidenceIndex): Geo {
  return {
    optimal: ev['ROUTE-OPTIMAL']?.data.geometry?.coordinates ?? [],
    actual: ev['ROUTE-ACTUAL']?.data.geometry?.coordinates ?? [],
    gps: ev['GPS-TRACE']?.data ?? [],
    prox: ev['PICKUP-PROXIMITY']?.data ?? null,
    traffic: Object.entries(ev)
      .filter(([, e]) => e.kind === 'traffic_event')
      .map(([k, e]) => ({ k, lat: e.data.near_lat, lng: e.data.near_lng, type: e.data.type })),
  }
}

export function geoFromTrip(trip: TripDetail): Geo {
  return {
    optimal: trip.optimal_route?.coordinates ?? [],
    actual: trip.actual_route?.coordinates ?? [],
    gps: [],
    prox: null,
    traffic: [],
  }
}

const TRAFFIC_LABEL: Record<string, string> = {
  construction: 'Roadworks',
  road_closure: 'Road closure',
  accident: 'Accident',
  congestion: 'Congestion',
}

export function TripMap({ geo, id, height = 220, legend = true }: { geo: Geo; id: string; height?: number; legend?: boolean }) {
  const { optimal: opt, actual: act, gps, prox, traffic } = geo
  const noShow = !!prox && !prox.reached_pickup
  const W = 420
  const H = Math.round(((W * height) / 420) * 0.62 + 120)
  const pad = 28
  // A no-show is about the driver's GPS against the pickup, so frame just those.
  const pts: LngLat[] = [
    ...(noShow ? [] : opt),
    ...(noShow ? [] : act),
    ...gps.map((p): LngLat => [p.lng, p.lat]),
    ...(prox ? [[prox.pickup.lng, prox.pickup.lat] as LngLat] : []),
    ...traffic.map((t): LngLat => [t.lng, t.lat]),
  ]
  if (!pts.length) return <p className="small muted" style={{ padding: 16 }}>No location data.</p>

  const lat0 = pts.reduce((a, p) => a + p[1], 0) / pts.length
  const kx = Math.cos((lat0 * Math.PI) / 180)
  const xs = pts.map((p) => p[0] * kx)
  const ys = pts.map((p) => p[1])
  let [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
  const span = 0.006
  if (x1 - x0 < span) { x0 -= span / 2; x1 += span / 2 }
  if (y1 - y0 < span) { y0 -= span / 2; y1 += span / 2 }
  const s = Math.min((W - 2 * pad) / (x1 - x0), (H - 2 * pad) / (y1 - y0))
  const ox = (W - (x1 - x0) * s) / 2
  const oy = (H - (y1 - y0) * s) / 2
  const px = (lng: number, lat: number): [number, number] => [ox + (lng * kx - x0) * s, oy + (y1 - lat) * s]
  const path = (c: LngLat[]) =>
    c.map(([lng, lat], i) => `${i ? 'L' : 'M'}${px(lng, lat).map((n) => n.toFixed(1)).join(' ')}`).join(' ')
  const mPerPx = 111320 / s
  const bar = [100, 200, 500, 1000, 2000, 5000].find((m) => m / mPerPx > 56) ?? 5000
  const start = act[0] ?? opt[0]
  const end = act[act.length - 1] ?? opt[opt.length - 1]
  const pickup = prox ? px(prox.pickup.lng, prox.pickup.lat) : null
  const nearest =
    noShow && gps.length
      ? gps.reduce(
          (b, p) => {
            const d = Math.hypot((p.lng - prox!.pickup.lng) * kx, p.lat - prox!.pickup.lat)
            return d < b.d ? { p, d } : b
          },
          { p: gps[0], d: Infinity },
        ).p
      : null
  const near = nearest ? px(nearest.lng, nearest.lat) : null
  const grid = `g${id.replace(/[^A-Za-z0-9]/g, '')}`

  return (
    <div>
      <svg className="map" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Map of the trip drawn from its GPS record">
        <defs>
          <pattern id={grid} width="28" height="28" patternUnits="userSpaceOnUse">
            <path d="M28 0H0V28" fill="none" stroke="var(--map-grid)" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width={W} height={H} fill={`url(#${grid})`} />
        {opt.length > 1 && !noShow && (
          <path d={path(opt)} fill="none" stroke="#9a9aa0" strokeWidth="4" strokeDasharray="2 9" strokeLinecap="round" />
        )}
        {act.length > 1 && !noShow && (
          <path d={path(act)} fill="none" stroke="var(--ink)" strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" />
        )}
        {noShow &&
          gps.map((p, i) => {
            const [x, y] = px(p.lng, p.lat)
            return <circle key={i} cx={x} cy={y} r="2.6" fill="var(--driver)" opacity=".8" />
          })}
        {pickup && noShow && (
          <g>
            <circle
              cx={pickup[0]} cy={pickup[1]} r={Math.max(prox!.arrival_radius_m / mPerPx, 7)}
              fill="color-mix(in srgb, var(--good) 14%, transparent)" stroke="var(--good)" strokeDasharray="3 3"
            />
            {near && (
              <>
                <line x1={pickup[0]} y1={pickup[1]} x2={near[0]} y2={near[1]} stroke="var(--warn)" strokeWidth="1.6" strokeDasharray="4 4" />
                <text x={(pickup[0] + near[0]) / 2 + 8} y={(pickup[1] + near[1]) / 2} style={{ fill: 'var(--warn)', font: '600 12px var(--font)' }}>
                  {prox!.closest_approach_m >= 1000 ? `${(prox!.closest_approach_m / 1000).toFixed(1)} km away` : `${Math.round(prox!.closest_approach_m)} m away`}
                </text>
              </>
            )}
          </g>
        )}
        {traffic.map((t) => {
          const [x, y] = px(t.lng, t.lat)
          return (
            <g key={t.k}>
              <path d={`M${x} ${y - 9}L${x + 8} ${y + 6}L${x - 8} ${y + 6}Z`} fill="var(--warn)" stroke="#fff" strokeWidth="1.5" />
              <text x={x + 12} y={y + 5} style={{ fill: 'var(--ink-2)', font: '500 11px var(--font)' }}>
                {TRAFFIC_LABEL[t.type ?? ''] ?? 'Traffic event'}
              </text>
            </g>
          )
        })}
        {start && !noShow && <circle cx={px(...start)[0]} cy={px(...start)[1]} r="7" fill="#fff" stroke="var(--ink)" strokeWidth="3" />}
        {end && !noShow && <rect x={px(...end)[0] - 6} y={px(...end)[1] - 6} width="12" height="12" rx="3" fill="var(--ink)" />}
        {noShow && pickup && (
          <g>
            <circle cx={pickup[0]} cy={pickup[1]} r="6" fill="var(--rider)" stroke="#fff" strokeWidth="2" />
            <text x={pickup[0] + 10} y={pickup[1] - 9} style={{ fill: 'var(--ink)', font: '600 12px var(--font)' }}>Pickup</text>
          </g>
        )}
        <g transform={`translate(${pad - 8}, ${H - 14})`}>
          <line x1="0" x2={bar / mPerPx} y1="0" y2="0" stroke="var(--ink-3)" strokeWidth="2" />
          <text x="0" y="-6" style={{ fill: 'var(--ink-3)', font: '500 11px var(--font)' }}>{bar >= 1000 ? `${bar / 1000} km` : `${bar} m`}</text>
        </g>
      </svg>
      {legend && (
        <div className="map-legend">
          {!noShow && opt.length > 1 && (
            <span>
              <svg width="18" height="4"><line x1="1" x2="17" y1="2" y2="2" stroke="#9a9aa0" strokeWidth="3" strokeDasharray="1 5" strokeLinecap="round" /></svg>
              Fastest route
            </span>
          )}
          {!noShow && act.length > 1 && (
            <span>
              <svg width="18" height="4"><line x1="1" x2="17" y1="2" y2="2" stroke="var(--ink)" strokeWidth="3" strokeLinecap="round" /></svg>
              Route driven
            </span>
          )}
          {noShow && (
            <>
              <span><svg width="10" height="10"><circle cx="5" cy="5" r="3" fill="var(--driver)" /></svg>Driver’s GPS</span>
              <span><svg width="12" height="12"><circle cx="6" cy="6" r="5" fill="none" stroke="var(--good)" strokeDasharray="2 2" /></svg>{prox!.arrival_radius_m} m arrival radius</span>
            </>
          )}
          {traffic.length > 0 && (
            <span><svg width="12" height="12"><path d="M6 1L11 10H1Z" fill="var(--warn)" /></svg>Recorded traffic events</span>
          )}
        </div>
      )}
    </div>
  )
}
