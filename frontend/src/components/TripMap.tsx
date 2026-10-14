import { useMemo } from 'react'
import { Circle, CircleMarker, MapContainer, Marker, Polyline, TileLayer, Tooltip } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { EvidenceIndex, TripDetail } from '../types/api'

/* The trip on a real street map: OneMap's grey basemap (Singapore Land Authority, the same
   service the trips' routes come from), with the fastest route dashed, the route driven
   solid, recorded traffic events, and for a no-show the driver's GPS fixes against the
   pickup's arrival radius, drawn to scale in metres. */

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

const TILES = 'https://www.onemap.gov.sg/maps/tiles/Grey/{z}/{x}/{y}.png'
const ATTRIBUTION =
  '<a href="https://www.onemap.gov.sg/" target="_blank" rel="noopener noreferrer">OneMap</a> © <a href="https://www.sla.gov.sg/" target="_blank" rel="noopener noreferrer">Singapore Land Authority</a>'

// Colours as literals: Leaflet paints SVG strokes, which can't read CSS variables.
const INK = '#1d1d1f'
const MUTED = '#8a8a8f'
const RIDER = '#6e4fd8'
const DRIVER = '#087a8c'
const GOOD = '#1d7f3a'
const WARN = '#a85400'

const toLatLng = ([lng, lat]: LngLat): [number, number] => [lat, lng]

const trafficIcon = L.divIcon({
  className: '',
  html: `<svg width="20" height="18" viewBox="0 0 20 18"><path d="M10 1L19 17H1Z" fill="${WARN}" stroke="#fff" stroke-width="1.5"/></svg>`,
  iconSize: [20, 18],
  iconAnchor: [10, 12],
})

function distanceLabel(m: number) {
  return m >= 1000 ? `${(m / 1000).toFixed(1)} km away` : `${Math.round(m)} m away`
}

export function TripMap({ geo, height = 220, legend = true }: { geo: Geo; id: string; height?: number; legend?: boolean }) {
  const { optimal: opt, actual: act, gps, prox, traffic } = geo
  const noShow = !!prox && !prox.reached_pickup

  // A no-show is about the driver's GPS against the pickup, so frame just those.
  const bounds = useMemo(() => {
    const pts: [number, number][] = [
      ...(noShow ? [] : opt.map(toLatLng)),
      ...(noShow ? [] : act.map(toLatLng)),
      ...gps.map((p): [number, number] => [p.lat, p.lng]),
      ...(prox ? [[prox.pickup.lat, prox.pickup.lng] as [number, number]] : []),
      ...traffic.map((t): [number, number] => [t.lat, t.lng]),
    ]
    return pts.length ? L.latLngBounds(pts) : null
  }, [noShow, opt, act, gps, prox, traffic])

  const nearest = useMemo(() => {
    if (!noShow || !gps.length || !prox) return null
    const p0 = L.latLng(prox.pickup.lat, prox.pickup.lng)
    return gps.reduce((b, p) => (p0.distanceTo([p.lat, p.lng]) < p0.distanceTo([b.lat, b.lng]) ? p : b), gps[0])
  }, [noShow, gps, prox])

  if (!bounds) return <p className="small muted" style={{ padding: 16 }}>No location data.</p>
  const start = act[0] ?? opt[0]
  const end = act[act.length - 1] ?? opt[opt.length - 1]
  // Remount when the trip changes, so the view refits to the new route.
  const key = `${bounds.toBBoxString()}:${noShow}`

  return (
    <div>
      <MapContainer
        key={key}
        className="trip-map"
        bounds={bounds}
        boundsOptions={{ padding: [28, 28], maxZoom: 17 }}
        style={{ height }}
        zoomControl={false}
        scrollWheelZoom={false}
        attributionControl
      >
        <TileLayer url={TILES} attribution={ATTRIBUTION} minZoom={11} maxZoom={19} detectRetina />
        {!noShow && opt.length > 1 && (
          <Polyline positions={opt.map(toLatLng)} pathOptions={{ color: MUTED, weight: 4, dashArray: '2 9', lineCap: 'round' }} />
        )}
        {!noShow && act.length > 1 && (
          <>
            <Polyline positions={act.map(toLatLng)} pathOptions={{ color: '#fff', weight: 8, opacity: 0.9 }} />
            <Polyline positions={act.map(toLatLng)} pathOptions={{ color: INK, weight: 4, lineJoin: 'round', lineCap: 'round' }} />
          </>
        )}
        {noShow &&
          gps.map((p, i) => (
            <CircleMarker key={i} center={[p.lat, p.lng]} radius={3} pathOptions={{ color: DRIVER, fillColor: DRIVER, fillOpacity: 0.85, weight: 0 }} />
          ))}
        {noShow && prox && (
          <>
            <Circle
              center={[prox.pickup.lat, prox.pickup.lng]}
              radius={prox.arrival_radius_m}
              pathOptions={{ color: GOOD, weight: 1.5, dashArray: '3 3', fillColor: GOOD, fillOpacity: 0.12 }}
            />
            {nearest && (
              <Polyline
                positions={[[prox.pickup.lat, prox.pickup.lng], [nearest.lat, nearest.lng]]}
                pathOptions={{ color: WARN, weight: 2, dashArray: '5 5' }}
              >
                <Tooltip permanent direction="center" className="map-label warn">{distanceLabel(prox.closest_approach_m)}</Tooltip>
              </Polyline>
            )}
            <CircleMarker center={[prox.pickup.lat, prox.pickup.lng]} radius={6} pathOptions={{ color: '#fff', weight: 2, fillColor: RIDER, fillOpacity: 1 }}>
              <Tooltip permanent direction="top" offset={[0, -6]} className="map-label">Pickup</Tooltip>
            </CircleMarker>
          </>
        )}
        {traffic.map((t) => (
          <Marker key={t.k} position={[t.lat, t.lng]} icon={trafficIcon}>
            <Tooltip permanent direction="right" offset={[8, -2]} className="map-label">{TRAFFIC_LABEL[t.type ?? ''] ?? 'Traffic event'}</Tooltip>
          </Marker>
        ))}
        {start && !noShow && (
          <CircleMarker center={toLatLng(start)} radius={6} pathOptions={{ color: INK, weight: 3, fillColor: '#fff', fillOpacity: 1 }} />
        )}
        {end && !noShow && (
          <CircleMarker center={toLatLng(end)} radius={6} pathOptions={{ color: '#fff', weight: 2, fillColor: INK, fillOpacity: 1 }} />
        )}
      </MapContainer>
      {legend && (
        <div className="map-legend">
          {!noShow && opt.length > 1 && (
            <span>
              <svg width="18" height="4"><line x1="1" x2="17" y1="2" y2="2" stroke={MUTED} strokeWidth="3" strokeDasharray="1 5" strokeLinecap="round" /></svg>
              Fastest route
            </span>
          )}
          {!noShow && act.length > 1 && (
            <span>
              <svg width="18" height="4"><line x1="1" x2="17" y1="2" y2="2" stroke={INK} strokeWidth="3" strokeLinecap="round" /></svg>
              Route driven
            </span>
          )}
          {noShow && prox && (
            <>
              <span><svg width="10" height="10"><circle cx="5" cy="5" r="3" fill={DRIVER} /></svg>Driver’s GPS</span>
              <span><svg width="12" height="12"><circle cx="6" cy="6" r="5" fill="none" stroke={GOOD} strokeDasharray="2 2" /></svg>{prox.arrival_radius_m} m arrival radius</span>
            </>
          )}
          {traffic.length > 0 && (
            <span><svg width="12" height="12"><path d="M6 1L11 10H1Z" fill={WARN} /></svg>Recorded traffic events</span>
          )}
        </div>
      )}
    </div>
  )
}
