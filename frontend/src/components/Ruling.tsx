import { useEffect, useState } from 'react'
import { counterfactual } from '../lib/counterfactual'
import { Ref, useEvidence } from '../lib/evidence'
import { money, outcomeLabel, remedyLabel, routesToL2 } from '../lib/format'
import type { Category, DecisionObject, EvidenceIndex } from '../types/api'
import { ConfidenceMeter } from './ConfidenceMeter'
import { GateChecks } from './GateChecks'

/**
 * A decision, laid out like a ruling: outcome and remedy, numbered findings that each
 * cite evidence you can open, the policy applied, how sure the Judge was against the
 * escalation threshold, what would have changed it, and whether it is final.
 */
export function Ruling({
  decision,
  category,
  title = 'Decision',
  stripped = [],
  gates = true,
}: {
  decision: DecisionObject
  category: Category | null
  title?: string
  stripped?: string[]
  gates?: boolean
}) {
  const ctx = useEvidence()
  const [index, setIndex] = useState<EvidenceIndex | null>(null)
  useEffect(() => {
    ctx?.load().then(setIndex, () => setIndex(null))
  }, [ctx])
  const cf = counterfactual(category, index)
  const pending = !decision.human_ratified && routesToL2(decision.escalation)
  const { remedy } = decision

  return (
    <article className="ruling">
      <div className="ruling-head">
        <div className="stack" style={{ gap: 6 }}>
          <span className="eyebrow">
            {title} · <span className="mono">{decision.case_id}</span>
          </span>
          <div className="ruling-outcome">{outcomeLabel(decision.outcome)}</div>
          <div className="ruling-remedy">
            {remedyLabel(remedy.type)}
            {remedy.amount != null && remedy.type !== 'no_action' && <> · {money(remedy.amount)}</>}
            {remedy.destination && <span className="faint"> → {remedy.destination.replaceAll('_', ' ')}</span>}
          </div>
        </div>
        <ConfidenceMeter value={decision.confidence} />
      </div>

      <div className="ruling-body">
        <div className="stack" style={{ gap: 8 }}>
          <span className="eyebrow">Findings</span>
          <ol className="findings">
            {decision.reasoning.map((f, i) => (
              <li key={i}>
                <div>
                  {f.finding}{' '}
                  {f.cites.map((c) => (
                    <Ref key={c} id={c} />
                  ))}
                </div>
              </li>
            ))}
          </ol>
          {stripped.length > 0 && (
            <p className="tiny muted">
              Removed by the citation validator, because they don’t exist in the case file:{' '}
              {stripped.map((s) => (
                <Ref key={s} id={s} stripped />
              ))}
            </p>
          )}
        </div>

        <div className="row" style={{ gap: 10 }}>
          <span className="eyebrow">Policy applied</span>
          {decision.policy_applied ? <Ref id={decision.policy_applied} /> : <span className="faint small">none</span>}
        </div>

        {cf && (
          <div className="counterfactual">
            <span className="eyebrow" style={{ display: 'block', marginBottom: 2 }}>
              What would change this
            </span>
            {cf}
          </div>
        )}

        {gates && <GateChecks escalation={decision.escalation} confidence={decision.confidence} />}
      </div>

      <div
        className={`status-strip ${decision.human_ratified ? 'tone-good' : pending ? 'tone-warn' : 'tone-good'}`}
      >
        {decision.human_ratified ? (
          <>
            <strong>Final.</strong> Reviewed by a person ({decision.ratified_by}).
          </>
        ) : pending ? (
          <>
            <strong>Not final.</strong> This is the agents’ recommendation; a human reviewer makes the
            decision.
          </>
        ) : (
          <>
            <strong>Final.</strong> Every gate passed, so the decision stands without review.
          </>
        )}
      </div>
    </article>
  )
}
