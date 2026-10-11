import type { Argument } from '../types/api'
import { Confidence } from './Confidence'

export function ArgumentCard({ argument, note }: { argument: Argument; note?: string | null }) {
  const label = argument.role === 'rider' ? 'Rider advocate' : 'Driver advocate'
  return (
    <article className={`agent-card ${argument.role}`}>
      <header>
        <span className="agent-name">{label}</span>
        <Confidence value={argument.confidence} />
      </header>
      <p>{argument.text}</p>
      <div className="refs">
        {argument.cites.map((c) => (
          <span key={c} className="chip" title="Evidence cited">
            {c}
          </span>
        ))}
        {argument.policy_cites.map((p) => (
          <span key={p} className="chip" title="Policy cited">
            {p}
          </span>
        ))}
      </div>
      {note && note !== 'argument validated' && (
        <p className="small" style={{ color: 'var(--warn)', marginTop: 8 }}>
          {note}
        </p>
      )}
    </article>
  )
}
