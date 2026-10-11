import type { Escalation } from '../types/api'
import { CONFIDENCE_THRESHOLD } from './ConfidenceMeter'

/**
 * The two-phase escalation gate and the compliance check, shown as what they are:
 * plain code that runs on every decision, whatever the Judge said.
 */
export function GateChecks({ escalation, confidence }: { escalation: Escalation; confidence: number }) {
  const bucketReasons = (escalation.reasons ?? [])
    .filter((r) => r.startsWith('bucket:'))
    .map((r) => r.replace(/^bucket: \w+ — /, ''))
  const judgeReason = (escalation.reasons ?? []).find((r) => r.startsWith('Judge requested'))
  const checks = [
    {
      pass: !escalation.confidence_escalate,
      title: `Confidence ≥ ${CONFIDENCE_THRESHOLD.toFixed(2)}`,
      text: escalation.confidence_escalate
        ? `${confidence.toFixed(2)} is below the threshold, so a person decides.`
        : `${confidence.toFixed(2)}: confident enough to stand without review.`,
    },
    {
      pass: !escalation.bucket_escalate,
      title: 'Risk bucket',
      text: escalation.bucket_escalate
        ? bucketReasons.join(' ') || 'This kind of case always goes to a person.'
        : 'Not a repeat filer, not a high-value fee, not safety.',
    },
    {
      pass: !escalation.judge_requested_escalation,
      title: 'Judge’s own request',
      text: escalation.judge_requested_escalation
        ? (judgeReason?.replace('Judge requested L2 review: ', '') ?? 'The Judge asked for a person.')
        : 'The Judge did not ask for review.',
    },
    {
      pass: !escalation.compliance_veto,
      title: 'Compliance check',
      text: escalation.compliance_veto
        ? `Vetoed: ${escalation.compliance_veto}`
        : 'Remedy matches the policy formula and caps.',
    },
  ]
  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="row between">
        <span className="eyebrow">Escalation gate and compliance</span>
        <span className="badge" title="Plain Python. No model is called, so the same case always gets the same result.">
          ◇ Deterministic · no model
        </span>
      </div>
      <div className="checks">
        {checks.map((c) => (
          <div key={c.title} className={`check ${c.pass ? 'check-pass' : 'check-flag'}`}>
            <span className="check-icon" aria-hidden>
              {c.pass ? '✓' : '!'}
            </span>
            <div>
              <strong>{c.title}</strong>
              <span className="sr-only">{c.pass ? ' passed' : ' flagged'}</span>
              <div className="muted">{c.text}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
