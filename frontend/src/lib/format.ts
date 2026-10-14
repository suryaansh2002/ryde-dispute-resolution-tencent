import type { CaseState, Category, Outcome, RemedyType } from '../types/api'

// Trips are in Singapore, so every time is shown in Singapore time wherever the viewer is.
const TZ = 'Asia/Singapore'

const moneyFmt = new Intl.NumberFormat('en-SG', {
  style: 'currency',
  currency: 'SGD',
  currencyDisplay: 'narrowSymbol',
})
const dayFmt = new Intl.DateTimeFormat('en-SG', { day: 'numeric', month: 'short', timeZone: TZ })
const timeFmt = new Intl.DateTimeFormat('en-SG', {
  hour: 'numeric',
  minute: '2-digit',
  hour12: false,
  timeZone: TZ,
})

const toDate = (iso: string) => new Date(iso.replace(' ', 'T'))

export const money = (n: number | string | null | undefined) =>
  n == null ? '—' : moneyFmt.format(Number(n))
export const day = (iso: string | null | undefined) => (iso ? dayFmt.format(toDate(iso)) : '—')
export const clock = (iso: string | null | undefined) => (iso ? timeFmt.format(toDate(iso)) : '—')
export const secs = (ms: number | null | undefined) =>
  ms == null ? '' : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`

export function ago(iso: string) {
  const h = (Date.now() - toDate(iso).getTime()) / 36e5
  if (h < 1) {
    const m = Math.max(1, Math.round(h * 60))
    return `${m} min`
  }
  if (h < 48) return `${Math.round(h)} h`
  return `${Math.round(h / 24)} days`
}

export const initials = (n: string) =>
  n.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase()
export const first = (n: string) => n.split(' ')[0]
export const minutesBetween = (a: string, b: string) =>
  Math.round((toDate(b).getTime() - toDate(a).getTime()) / 60000)
export const secondsBetween = (a: string, b: string) =>
  (toDate(b).getTime() - toDate(a).getTime()) / 1000

/** What the parties call each kind of dispute. */
export const CAT: Record<Category, string> = {
  route_deviation: 'Longer route',
  no_show_charge: 'No-show fee',
  property_damage: 'Cleaning fee',
  safety_incident: 'Safety report',
}
/** What support and the trace call it. */
export const CAT_FULL: Record<Category, string> = {
  route_deviation: 'Route deviation',
  no_show_charge: 'No-show charge',
  property_damage: 'Property damage',
  safety_incident: 'Safety incident',
}
export const OUTCOME: Record<Outcome, string> = {
  claim_upheld: 'Claim upheld',
  claim_upheld_partial: 'Partly upheld',
  claim_denied: 'Claim denied',
  declined_insufficient_evidence: 'Declined, can refile',
}
export const outcomeLabel = (o: string | null | undefined) =>
  o ? (OUTCOME as Record<string, string>)[o] ?? o : '—'
export const REMEDY: Record<RemedyType, string> = {
  partial_refund: 'Refund',
  full_refund: 'Full refund',
  no_show_fee_waiver: 'Fee waived',
  cleaning_repair_fee: 'Cleaning fee',
  no_action: 'No action',
  compensation_credit: 'Credit',
}

/** States a case passes through before anything is final. */
export const IN_PROGRESS: CaseState[] = ['opened', 'triage', 'assembling', 'awaiting_response', 'adjudicating']
export const isFinal = (s: CaseState) => !IN_PROGRESS.includes(s)

export type Tone = 'good' | 'warn' | 'bad' | 'neutral' | 'live'
export function statusPill(state: CaseState): [Tone, string] {
  switch (state) {
    case 'decided':
      return ['good', 'Decided']
    case 'escalated':
      return ['warn', 'With a person']
    case 'safety_bypassed':
      return ['bad', 'Safety team']
    case 'declined_insufficient_evidence':
      return ['neutral', 'Declined']
    case 'awaiting_response':
      return ['live', 'Waiting for a reply']
    default:
      return ['live', 'In progress']
  }
}

export const band = (conf: number) => (conf >= 0.85 ? 'High' : conf >= 0.6 ? 'Moderate' : 'Low')
