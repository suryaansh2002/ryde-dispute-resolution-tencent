import { Ref } from '../lib/evidence'
import { tierLabel } from '../lib/format'
import type { DamageFinding } from '../types/api'

/** One Image Analysis result: what the vision model saw, and the tier code mapped it to. */
export function PhotoFinding({ id, finding }: { id?: string; finding: DamageFinding }) {
  const tone = finding.tier === 'unclear' ? 'tone-warn' : ''
  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="row" style={{ gap: 6 }}>
        {id && <Ref id={id} />}
        <span className="badge">{finding.mess_type.replaceAll('_', ' ')}</span>
        <span className="badge">{finding.extent} area</span>
        <span className={`badge ${tone}`}>{tierLabel(finding.tier)}</span>
        <span className="tiny faint mono">conf {finding.confidence.toFixed(2)}</span>
      </div>
      <p className="small muted">{finding.description}</p>
    </div>
  )
}
