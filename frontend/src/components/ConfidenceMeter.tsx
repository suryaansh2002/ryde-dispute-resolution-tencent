/** Confidence with the escalation threshold marked: below the tick, a human decides. */
export const CONFIDENCE_THRESHOLD = 0.6

export function ConfidenceMeter({ value, label = 'Confidence' }: { value: number; label?: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100)
  const below = value < CONFIDENCE_THRESHOLD
  return (
    <div className="meter" title={`Escalation threshold ${CONFIDENCE_THRESHOLD}: below it, a human reviewer decides.`}>
      <div className="meter-labels">
        <span>{label}</span>
        <span className="mono" style={{ color: below ? 'var(--warn)' : 'var(--ink)' }}>
          {(value).toFixed(2)}
        </span>
      </div>
      <div className="meter-track">
        <div className="meter-fill" style={{ width: `${pct}%`, background: below ? 'var(--warn)' : undefined }} />
        <div className="meter-tick" style={{ left: `calc(${CONFIDENCE_THRESHOLD * 100}% - 1px)` }} />
      </div>
    </div>
  )
}
