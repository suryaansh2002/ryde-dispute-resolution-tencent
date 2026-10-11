import { IN_PROGRESS, STATE_LABEL, STATE_TONE, toneClass } from '../lib/format'
import type { CaseState } from '../types/api'

export function StateBadge({ state }: { state: CaseState }) {
  const live = IN_PROGRESS.includes(state)
  return (
    <span className={`badge ${toneClass(STATE_TONE[state] ?? 'neutral')}`}>
      <span className={`dot${live ? ' pulse' : ''}`} />
      {STATE_LABEL[state] ?? state}
    </span>
  )
}
