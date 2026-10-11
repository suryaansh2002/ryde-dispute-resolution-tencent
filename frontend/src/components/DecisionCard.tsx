import { money, outcomeLabel, remedyLabel } from '../lib/format'
import type { DecisionObject } from '../types/api'
import { Confidence } from './Confidence'

export function DecisionCard({ decision, title = 'Judge' }: { decision: DecisionObject; title?: string }) {
  const esc = decision.escalation
  const toL2 =
    esc.bucket_escalate ||
    esc.confidence_escalate ||
    esc.judge_requested_escalation ||
    Boolean(esc.compliance_veto)
  return (
    <article className="agent-card judge">
      <header>
        <span className="agent-name">{title}</span>
        <Confidence value={decision.confidence} />
      </header>
      <div className="row" style={{ marginBottom: 8 }}>
        <strong>{outcomeLabel(decision.outcome)}</strong>
        <span className="muted">·</span>
        <span>
          {remedyLabel(decision.remedy.type)}
          {decision.remedy.amount ? ` ${money(decision.remedy.amount)}` : ''}
        </span>
        {decision.policy_applied && <span className="chip">{decision.policy_applied}</span>}
        {decision.human_ratified && (
          <span className="badge tone-good">Ratified by {decision.ratified_by}</span>
        )}
      </div>
      <ol className="findings">
        {decision.reasoning.map((f, i) => (
          <li key={i}>
            {f.finding}{' '}
            {f.cites.map((c) => (
              <span key={c} className="chip" style={{ marginRight: 3 }}>
                {c}
              </span>
            ))}
          </li>
        ))}
      </ol>
      {toL2 && !decision.human_ratified && (
        <div className="callout tone-warn" style={{ marginTop: 8 }}>
          <strong>Escalated to human review</strong>
          <ul>
            {(esc.reasons ?? []).map((r, i) => (
              <li key={i}>{r}</li>
            ))}
            {esc.compliance_veto && <li>Compliance veto: {esc.compliance_veto}</li>}
          </ul>
        </div>
      )}
    </article>
  )
}
