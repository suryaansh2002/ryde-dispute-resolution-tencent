export function Confidence({ value }: { value: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100)
  return (
    <span className="confidence" title="Model-reported confidence">
      <span className="bar">
        <span className="fill" style={{ width: `${pct}%` }} />
      </span>
      {pct}%
    </span>
  )
}
