import type { CaseState, Category, Escalation, Outcome, RemedyType } from '../types/api'

export const CATEGORY_LABEL: Record<Category, string> = {
  route_deviation: 'Route deviation',
  no_show_charge: 'No-show charge',
  property_damage: 'Property damage',
  safety_incident: 'Safety incident',
}

export const STATE_LABEL: Record<CaseState, string> = {
  opened: 'Opened',
  triage: 'Triage',
  assembling: 'Gathering evidence',
  awaiting_response: 'Awaiting response',
  adjudicating: 'Adjudicating',
  decided: 'Decided',
  escalated: 'Human review',
  safety_bypassed: 'Safety — human review',
  declined_insufficient_evidence: 'Declined',
}

export type Tone = 'neutral' | 'progress' | 'good' | 'warn' | 'bad'

export const STATE_TONE: Record<CaseState, Tone> = {
  opened: 'progress',
  triage: 'progress',
  assembling: 'progress',
  awaiting_response: 'neutral',
  adjudicating: 'progress',
  decided: 'good',
  escalated: 'warn',
  safety_bypassed: 'bad',
  declined_insufficient_evidence: 'neutral',
}

export const IN_PROGRESS: CaseState[] = ['opened', 'triage', 'assembling', 'adjudicating']

export const OUTCOME_LABEL: Record<Outcome, string> = {
  claim_upheld: 'Claim upheld',
  claim_upheld_partial: 'Claim partially upheld',
  claim_denied: 'Claim denied',
  declined_insufficient_evidence: 'Declined — insufficient evidence',
}

export const REMEDY_LABEL: Record<RemedyType, string> = {
  full_refund: 'Full refund',
  partial_refund: 'Partial refund',
  compensation_credit: 'Compensation credit',
  cleaning_repair_fee: 'Cleaning fee',
  no_show_fee_waiver: 'No-show fee waived',
  no_action: 'No action',
}

export const money = (n: number | null | undefined) =>
  n == null ? '—' : `$${n.toFixed(2)}`

export function when(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function outcomeLabel(outcome: string): string {
  return OUTCOME_LABEL[outcome as Outcome] ?? outcome
}

export function remedyLabel(type: string): string {
  return REMEDY_LABEL[type as RemedyType] ?? type
}

export const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  })

export function duration(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  if (seconds < 90) return `${Math.round(seconds)} s`
  if (seconds < 5400) return `${Math.round(seconds / 60)} min`
  return `${(seconds / 3600).toFixed(1)} h`
}

export function ago(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return 'just now'
  return `${duration(s)} ago`
}

/** True when the deterministic gate or compliance sent the decision to a human. */
export function routesToL2(esc: Escalation | null | undefined): boolean {
  return Boolean(
    esc && (esc.bucket_escalate || esc.confidence_escalate || esc.judge_requested_escalation || esc.compliance_veto),
  )
}

/** Why a case is in front of a human, as short labels for the L2 queue. */
export function whyLabels(item: { is_safety: boolean; escalation: Escalation | null }): { label: string; tone: Tone }[] {
  if (item.is_safety) return [{ label: 'Safety', tone: 'bad' }]
  const esc = item.escalation
  if (!esc) return []
  const out: { label: string; tone: Tone }[] = []
  for (const r of esc.reasons ?? []) {
    if (r.startsWith('bucket: repeat_filer')) out.push({ label: 'Repeat filer', tone: 'warn' })
    if (r.startsWith('bucket: high_value')) out.push({ label: 'High-value fee', tone: 'warn' })
    if (r.startsWith('bucket: safety')) out.push({ label: 'Safety', tone: 'bad' })
  }
  if (esc.confidence_escalate) out.push({ label: 'Low confidence', tone: 'warn' })
  if (esc.judge_requested_escalation) out.push({ label: 'Judge asked', tone: 'neutral' })
  if (esc.compliance_veto) out.push({ label: 'Compliance veto', tone: 'bad' })
  return out
}

export const toneClass = (tone: Tone) =>
  tone === 'progress' ? 'tone-live' : tone === 'neutral' ? '' : `tone-${tone}`

export const TIER_FEE: Record<string, number> = { minor: 40, moderate: 120, severe: 200 }

export function tierLabel(tier: string): string {
  if (tier in TIER_FEE) return `${tier[0].toUpperCase()}${tier.slice(1)} tier · $${TIER_FEE[tier]}`
  if (tier === 'none') return 'No mess visible'
  return 'Unclear: a person decides'
}
