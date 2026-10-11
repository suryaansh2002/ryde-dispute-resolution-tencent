import { Ref } from '../lib/evidence'
import { strippedRefs } from '../lib/strip'
import type { Argument } from '../types/api'

export function ArgumentCard({ argument, note }: { argument: Argument; note?: string | null }) {
  const label = argument.role === 'rider' ? 'Rider advocate' : 'Driver advocate'
  const stripped = strippedRefs(note)
  return (
    <article className={`card ${argument.role}`}>
      <div className="card-head">
        <span className="agent-label">{label}</span>
        <span className="tiny faint mono" title="How strongly the advocate rates its own side">
          self-rated {argument.confidence.toFixed(2)}
        </span>
      </div>
      <p className="small" style={{ whiteSpace: 'pre-wrap' }}>
        {argument.text}
      </p>
      <div className="refs">
        {argument.cites.map((c) => (
          <Ref key={c} id={c} />
        ))}
        {argument.policy_cites.map((p) => (
          <Ref key={p} id={p} />
        ))}
        {stripped.map((s) => (
          <Ref key={s} id={s} stripped />
        ))}
      </div>
      {stripped.length > 0 && (
        <p className="tiny" style={{ color: 'var(--bad)', marginTop: 8 }}>
          {stripped.length} citation{stripped.length > 1 ? 's' : ''} removed: not in the case file.
        </p>
      )}
    </article>
  )
}
