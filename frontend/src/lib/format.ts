import type { CaseState, Category, Outcome, RemedyType } from '../types/api'

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
