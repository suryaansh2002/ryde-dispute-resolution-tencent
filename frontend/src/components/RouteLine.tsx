import type { Station, StationId, StationStatus } from '../lib/pipeline'

/*
 * The case's route through the system, drawn as a transit line. Agents are circles,
 * deterministic rules are diamonds, the human step is a rounded square. At the hearing
 * the line splits into a rider track (blue) and a driver track (magenta) that rejoin at
 * the Judge: the only colour on the map belongs to the two parties.
 */

const MAIN_Y = 78
const RIDER_Y = 40
const DRIVER_Y = 116

const POS: Record<StationId, { x: number; y: number }> = {
  claim: { x: 34, y: MAIN_Y },
  triage: { x: 128, y: MAIN_Y },
  prevention: { x: 228, y: MAIN_Y },
  evidence: { x: 328, y: MAIN_Y },
  response: { x: 432, y: MAIN_Y },
  rider: { x: 548, y: RIDER_Y },
  driver: { x: 548, y: DRIVER_Y },
  judge: { x: 666, y: MAIN_Y },
  gate: { x: 768, y: MAIN_Y },
  compliance: { x: 862, y: MAIN_Y },
  outcome: { x: 960, y: MAIN_Y },
}

const reached = (s: StationStatus) => s !== 'idle'

function trackColor(to: Station, party?: 'rider' | 'driver') {
  if (!reached(to.status)) return 'var(--line-strong)'
  if (party) return `var(--${party})`
  if (to.status === 'flagged') return 'var(--warn)'
  return 'var(--ink)'
}

function Glyph({ station, selected }: { station: Station; selected?: boolean }) {
  const { x, y } = POS[station.id]
  const party = station.id === 'rider' || station.id === 'driver' ? station.id : null
  const filled =
    station.status === 'done'
      ? party
        ? `var(--${party})`
        : 'var(--ink)'
      : station.status === 'flagged'
        ? 'var(--warn)'
        : station.status === 'stopped'
          ? 'var(--ink-3)'
          : 'var(--surface)'
  const stroke =
    station.status === 'idle'
      ? 'var(--line-strong)'
      : station.status === 'flagged'
        ? 'var(--warn)'
        : party && station.status === 'active'
          ? `var(--${party})`
          : station.status === 'stopped'
            ? 'var(--ink-3)'
            : 'var(--ink)'
  const dash = station.status === 'skipped' ? '3 3' : undefined
  const ringColor = party ? `var(--${party})` : 'var(--ink)'

  let shape
  if (station.kind === 'rule') {
    shape = (
      <rect
        x={x - 8}
        y={y - 8}
        width={16}
        height={16}
        transform={`rotate(45 ${x} ${y})`}
        fill={filled}
        stroke={stroke}
        strokeWidth={2.2}
        strokeDasharray={dash}
      />
    )
  } else if (station.kind === 'human') {
    shape = (
      <rect x={x - 9} y={y - 9} width={18} height={18} rx={5} fill={filled} stroke={stroke} strokeWidth={2.2} strokeDasharray={dash} />
    )
  } else if (station.kind === 'endpoint') {
    shape = <circle cx={x} cy={y} r={station.id === 'outcome' ? 10 : 7} fill={filled} stroke={stroke} strokeWidth={2.2} />
  } else {
    shape = <circle cx={x} cy={y} r={10} fill={filled} stroke={stroke} strokeWidth={2.2} strokeDasharray={dash} />
  }

  const labelAbove = station.id === 'rider'
  const labelY = labelAbove ? y - 22 : y + 28
  return (
    <g className={`station${station.status === 'active' ? ' station-active' : ''}`}>
      {station.status === 'active' && (
        <circle className="ring" cx={x} cy={y} r={17} fill="none" stroke={ringColor} strokeWidth={1.5} opacity={0.6} />
      )}
      {selected && <circle cx={x} cy={y} r={20} fill="none" stroke="var(--ink-3)" strokeDasharray="2 3" />}
      {shape}
      {station.status === 'done' && station.kind !== 'endpoint' && (
        <path
          d={`M ${x - 4} ${y} l 3 3 l 5 -6`}
          fill="none"
          stroke="var(--on-ink)"
          strokeWidth={1.8}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      )}
      {station.status === 'flagged' && (
        <text x={x} y={y + 4} textAnchor="middle" style={{ fill: 'var(--on-ink)', fontSize: 11, fontWeight: 700 }}>
          !
        </text>
      )}
      <text x={x} y={labelY} textAnchor="middle">
        {station.label}
      </text>
      {station.note && (
        <text className="sub" x={x} y={labelAbove ? labelY - 13 : labelY + 14} textAnchor="middle">
          {station.note}
        </text>
      )}
    </g>
  )
}

export function RouteLine({
  stations,
  onSelect,
  selected,
}: {
  stations: Station[]
  onSelect?: (id: StationId) => void
  selected?: StationId | null
}) {
  const by = Object.fromEntries(stations.map((s) => [s.id, s])) as Record<StationId, Station>
  const seg = (a: StationId, b: StationId) => (
    <line
      key={`${a}-${b}`}
      x1={POS[a].x}
      y1={POS[a].y}
      x2={POS[b].x}
      y2={POS[b].y}
      stroke={trackColor(by[b])}
      strokeWidth={4}
      strokeLinecap="round"
    />
  )
  // The split: response → rider/driver, and back into the judge.
  const branch = (party: 'rider' | 'driver') => {
    const r = POS.response
    const p = POS[party]
    const j = POS.judge
    const out = `M ${r.x} ${r.y} C ${r.x + 50} ${r.y}, ${p.x - 60} ${p.y}, ${p.x} ${p.y}`
    const back = `M ${p.x} ${p.y} C ${p.x + 60} ${p.y}, ${j.x - 50} ${j.y}, ${j.x} ${j.y}`
    return (
      <g key={party}>
        <path d={out} fill="none" stroke={trackColor(by[party], party)} strokeWidth={4} strokeLinecap="round" />
        <path d={back} fill="none" stroke={trackColor(by.judge, reached(by.judge.status) ? party : undefined)} strokeWidth={4} strokeLinecap="round" />
      </g>
    )
  }

  return (
    <div className="routemap-wrap">
      <svg className="routemap" viewBox="0 0 1000 158" role="img" aria-label="Pipeline progress for this case">
        {seg('claim', 'triage')}
        {seg('triage', 'prevention')}
        {seg('prevention', 'evidence')}
        {seg('evidence', 'response')}
        {branch('rider')}
        {branch('driver')}
        {seg('judge', 'gate')}
        {seg('gate', 'compliance')}
        {seg('compliance', 'outcome')}
        {stations.map((s) => (
          <g key={s.id} onClick={() => onSelect?.(s.id)}>
            <title>{`${s.label}: ${s.status}${s.note ? ` (${s.note})` : ''}`}</title>
            <Glyph station={s} selected={selected === s.id} />
          </g>
        ))}
      </svg>
    </div>
  )
}

export function RouteLegend() {
  return (
    <div className="legend">
      <span>
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
          <circle cx="7" cy="7" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
        </svg>
        AI agent
      </span>
      <span>
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
          <rect x="3" y="3" width="8" height="8" transform="rotate(45 7 7)" fill="none" stroke="currentColor" strokeWidth="1.6" />
        </svg>
        Deterministic rule, no model
      </span>
      <span>
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
          <rect x="2" y="2" width="10" height="10" rx="3" fill="none" stroke="currentColor" strokeWidth="1.6" />
        </svg>
        Person
      </span>
      <span className="party rider">Rider’s side</span>
      <span className="party driver">Driver’s side</span>
    </div>
  )
}
