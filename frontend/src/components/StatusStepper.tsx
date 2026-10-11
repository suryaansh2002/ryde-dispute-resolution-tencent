import type { Station, StationId } from '../lib/pipeline'

const STEPS: { label: string; stations: StationId[] }[] = [
  { label: 'Reported', stations: ['claim'] },
  { label: 'Checked', stations: ['triage', 'prevention'] },
  { label: 'Evidence', stations: ['evidence'] },
  { label: 'Other side', stations: ['response'] },
  { label: 'Hearing', stations: ['rider', 'driver', 'judge'] },
  { label: 'Decision', stations: ['outcome'] },
]

/** The party's view of the pipeline: six plain steps instead of eleven stations. */
export function StatusStepper({ stations }: { stations: Station[] }) {
  const by = Object.fromEntries(stations.map((s) => [s.id, s])) as Record<StationId, Station>
  const stoppedAt = STEPS.findIndex((step) => step.stations.some((id) => by[id].status === 'stopped'))
  return (
    <ol className="stepper" aria-label="Progress" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
      {STEPS.map((step, i) => {
        const ss = step.stations.map((id) => by[id])
        const stopped = ss.some((s) => s.status === 'stopped')
        const flagged = ss.some((s) => s.status === 'flagged')
        const allDone = ss.every((s) => s.status === 'done' || s.status === 'skipped')
        const active = ss.some((s) => s.status === 'active') || (allDone === false && ss.some((s) => s.status === 'done'))
        const after = stoppedAt >= 0 && i > stoppedAt
        const cls = after ? '' : stopped ? 'stopped' : flagged ? 'current' : allDone ? 'done' : active ? 'current' : ''
        return (
          <li key={step.label} className={`step ${cls}`} aria-current={cls === 'current' ? 'step' : undefined}>
            <span className="step-bar" />
            <span>{step.label}</span>
          </li>
        )
      })}
    </ol>
  )
}
