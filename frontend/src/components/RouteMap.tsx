import type { EvidenceIndex } from '../types/api'

/*
 * A schematic map of the trip, drawn from the case file itself: the planned route
 * (dashed), the route actually driven (solid), the GPS fixes, the pickup point with
 * the 100 m arrival radius, and any recorded traffic events. No map tiles: everything
 * on it is evidence the agents could cite, at true relative scale, with a scale bar.
 */

type LngLat = [number, number]

const W = 520
const H = 300
const PAD = 30

const NICE_METRES = [50, 100, 200, 250, 500, 1000, 2000, 5000, 10000]

export function RouteMap({ index, focus }: { index: EvidenceIndex; focus?: string }) {
  const optimal: LngLat[] = index['ROUTE-OPTIMAL']?.data?.geometry?.coordinates ?? []
  const actual: LngLat[] = index['ROUTE-ACTUAL']?.data?.geometry?.coordinates ?? []
  const gps: { lat: number; lng: number }[] = index['GPS-TRACE']?.data ?? []
  const prox = index['PICKUP-PROXIMITY']?.data as
    | { pickup: { lat: number; lng: number }; closest_approach_m: number; arrival_radius_m: number; reached_pickup: boolean }
    | undefined
  const traffic = Object.entries(index)
    .filter(([, item]) => item.kind === 'traffic_event')
    .map(([ref, item]) => ({ ref, lat: item.data.near_lat as number, lng: item.data.near_lng as number, type: item.data.type as string }))

  const points: LngLat[] = [
    ...optimal,
    ...actual,
    ...gps.map((p) => [p.lng, p.lat] as LngLat),
    ...(prox ? [[prox.pickup.lng, prox.pickup.lat] as LngLat] : []),
    ...traffic.map((t) => [t.lng, t.lat] as LngLat),
  ]
  if (points.length === 0) return <p className="muted small">No location data in this case file.</p>

  const meanLat = points.reduce((a, p) => a + p[1], 0) / points.length
  const kx = Math.cos((meanLat * Math.PI) / 180)
  const xs = points.map((p) => p[0] * kx)
  const ys = points.map((p) => p[1])
  let [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
  // Pad a degenerate box (a driver parked in one place) so it still draws.
  const minSpan = 0.004
  if (maxX - minX < minSpan) [minX, maxX] = [minX - minSpan / 2, maxX + minSpan / 2]
  if (maxY - minY < minSpan) [minY, maxY] = [minY - minSpan / 2, maxY + minSpan / 2]
  const scale = Math.min((W - 2 * PAD) / (maxX - minX), (H - 2 * PAD) / (maxY - minY))
  const offX = (W - (maxX - minX) * scale) / 2
  const offY = (H - (maxY - minY) * scale) / 2
  const px = (lng: number, lat: number): [number, number] => [
    offX + (lng * kx - minX) * scale,
    offY + (maxY - lat) * scale,
  ]
  const path = (coords: LngLat[]) =>
    coords.map(([lng, lat], i) => `${i ? 'L' : 'M'} ${px(lng, lat).map((n) => n.toFixed(1)).join(' ')}`).join(' ')

  // Scale: one degree of latitude is about 111,320 m.
  const pxPerMetre = scale / 111_320
  const barMetres = NICE_METRES.find((m) => m * pxPerMetre >= W * 0.14) ?? 10000
  const barPx = barMetres * pxPerMetre
  const barLabel = barMetres >= 1000 ? `${barMetres / 1000} km` : `${barMetres} m`

  const start = actual[0] ?? optimal[0]
  const end = actual[actual.length - 1] ?? optimal[optimal.length - 1]
  const pickup = prox ? px(prox.pickup.lng, prox.pickup.lat) : null
  const nearest = prox && gps.length
    ? gps.reduce((best, p) => {
        const d = Math.hypot((p.lng - prox.pickup.lng) * kx, p.lat - prox.pickup.lat)
        return d < best.d ? { p, d } : best
      }, { p: gps[0], d: Infinity }).p
    : null

  return (
    <div className="mapbox">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Map of the trip from the case file">
        <defs>
          <pattern id="grid" width="26" height="26" patternUnits="userSpaceOnUse">
            <path d="M 26 0 L 0 0 0 26" fill="none" stroke="var(--line)" strokeWidth="0.6" />
          </pattern>
        </defs>
        <rect width={W} height={H} fill="url(#grid)" />

        {optimal.length > 1 && (
          <path d={path(optimal)} fill="none" stroke="var(--ink-3)" strokeWidth={3} strokeDasharray="7 6" strokeLinecap="round" />
        )}
        {actual.length > 1 && (
          <path
            d={path(actual)}
            fill="none"
            stroke="var(--ink)"
            strokeWidth={focus === 'route' ? 4 : 3}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        )}
        {gps.map((p, i) => {
          const [x, y] = px(p.lng, p.lat)
          return <circle key={i} cx={x} cy={y} r={focus === 'gps' ? 2.6 : 1.8} fill="var(--ink-2)" opacity={0.75} />
        })}

        {pickup && prox && (
          <g>
            <circle
              cx={pickup[0]}
              cy={pickup[1]}
              r={Math.max(prox.arrival_radius_m * pxPerMetre, 4)}
              fill="color-mix(in srgb, var(--good) 14%, transparent)"
              stroke="var(--good)"
              strokeDasharray="3 3"
            />
            {nearest && !prox.reached_pickup && (
              <>
                <line
                  x1={pickup[0]}
                  y1={pickup[1]}
                  x2={px(nearest.lng, nearest.lat)[0]}
                  y2={px(nearest.lng, nearest.lat)[1]}
                  stroke="var(--warn)"
                  strokeWidth={1.6}
                  strokeDasharray="4 3"
                />
                <text
                  x={px(nearest.lng, nearest.lat)[0] + 10}
                  y={px(nearest.lng, nearest.lat)[1] + 16}
                  style={{ fill: 'var(--warn)', font: '600 11px var(--font-mono)' }}
                >
                  {Math.round(prox.closest_approach_m)} m
                </text>
              </>
            )}
          </g>
        )}

        {traffic.map((t) => {
          const [x, y] = px(t.lng, t.lat)
          return (
            <g key={t.ref}>
              <path d={`M ${x} ${y - 8} L ${x + 7} ${y + 5} L ${x - 7} ${y + 5} Z`} fill="var(--warn)" stroke="var(--surface)" strokeWidth={1.5} />
              <text x={x + 10} y={y + 4} style={{ fill: 'var(--ink-2)', font: '500 10.5px var(--font-mono)' }}>
                {t.ref} · {t.type.replace('_', ' ')}
              </text>
            </g>
          )
        })}

        {start && (
          <g>
            <circle cx={px(...start)[0]} cy={px(...start)[1]} r={6} fill="var(--surface)" stroke="var(--ink)" strokeWidth={2.4} />
            <text x={px(...start)[0] + 10} y={px(...start)[1] - 8} style={{ fill: 'var(--ink)', font: '600 11px var(--font-cond)' }}>
              PICKUP
            </text>
          </g>
        )}
        {end && (
          <g>
            <rect x={px(...end)[0] - 6} y={px(...end)[1] - 6} width={12} height={12} fill="var(--ink)" />
            <text x={px(...end)[0] + 10} y={px(...end)[1] + 4} style={{ fill: 'var(--ink)', font: '600 11px var(--font-cond)' }}>
              DROP-OFF
            </text>
          </g>
        )}
        {!start && pickup && (
          <text x={pickup[0] + 10} y={pickup[1] - 8} style={{ fill: 'var(--ink)', font: '600 11px var(--font-cond)' }}>
            PICKUP
          </text>
        )}

        <g transform={`translate(${PAD - 14}, ${H - 12})`}>
          <line x1={0} y1={0} x2={barPx} y2={0} stroke="var(--ink-2)" strokeWidth={2} />
          <line x1={0} y1={-4} x2={0} y2={4} stroke="var(--ink-2)" strokeWidth={2} />
          <line x1={barPx} y1={-4} x2={barPx} y2={4} stroke="var(--ink-2)" strokeWidth={2} />
          <text x={barPx / 2} y={-7} textAnchor="middle" style={{ fill: 'var(--ink-2)', font: '500 10.5px var(--font-mono)' }}>
            {barLabel}
          </text>
        </g>
      </svg>
      <div className="legend" style={{ padding: '8px 12px', borderTop: '1px solid var(--line)' }}>
        {optimal.length > 1 && <span>┄ planned route</span>}
        {actual.length > 1 && <span>━ route driven</span>}
        {gps.length > 0 && <span>· GPS fixes ({gps.length})</span>}
        {prox && <span style={{ color: 'var(--good)' }}>◌ {prox.arrival_radius_m} m arrival radius</span>}
        {traffic.length > 0 && <span style={{ color: 'var(--warn)' }}>▲ traffic event</span>}
      </div>
    </div>
  )
}
