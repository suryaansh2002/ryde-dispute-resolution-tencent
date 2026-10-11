// Mirrors of the backend's locked schemas (backend/app/schemas) and API payloads.
// Keep in sync by hand; the backend is the source of truth.

export type Role = 'rider' | 'driver'

export type Category = 'route_deviation' | 'no_show_charge' | 'property_damage' | 'safety_incident'

export type CaseState =
  | 'opened'
  | 'triage'
  | 'assembling'
  | 'awaiting_response'
  | 'adjudicating'
  | 'decided'
  | 'escalated'
  | 'safety_bypassed'
  | 'declined_insufficient_evidence'

export type Outcome =
  | 'claim_upheld'
  | 'claim_upheld_partial'
  | 'claim_denied'
  | 'declined_insufficient_evidence'

export type RemedyType =
  | 'full_refund'
  | 'partial_refund'
  | 'compensation_credit'
  | 'cleaning_repair_fee'
  | 'no_show_fee_waiver'
  | 'no_action'

export interface Remedy {
  type: RemedyType
  amount?: number | null
  destination?: string | null
}

export interface Finding {
  finding: string
  cites: string[]
}

export interface Escalation {
  bucket: 'agent_decidable' | 'always_escalate'
  bucket_escalate: boolean
  confidence_escalate: boolean
  judge_requested_escalation: boolean
  compliance_veto?: string | null
  reasons?: string[]
}

export interface DecisionObject {
  case_id: string
  outcome: Outcome | string
  remedy: Remedy
  reasoning: Finding[]
  policy_applied: string | null
  confidence: number
  escalation: Escalation
  human_ratified: boolean
  ratified_by: string | null
}

export interface Argument {
  role: Role
  text: string
  cites: string[]
  policy_cites: string[]
  confidence: number
}

export interface TriageResult {
  category: Category
  tier: string
  is_safety: boolean
}

export interface PolicyTag {
  chunk_id: string
  policy_id: string
  excerpt: string
}

export interface CaseFile {
  case_id: string
  category: Category
  complainer_role: Role
  chat_log: { id: string; sender_role: Role; timestamp: string; text: string }[]
  gps_trace: unknown[]
  photos: { evidence_id: string }[]
  traffic_events: unknown[]
  payment: { total_fare: number; add_on_fees: { type: string; amount: number }[] }
  policy_tags: PolicyTag[]
}

export type TraceKind =
  | 'state_transition'
  | 'rule_evaluation'
  | 'agent_start'
  | 'agent_complete'
  | 'agent_output'
  | 'tool_call'
  | 'escalation'
  | 'l2_review'
  | 'error'

export type AgentName =
  | 'triage'
  | 'evidence_collection'
  | 'rider_advocate'
  | 'driver_advocate'
  | 'judge'

export interface TraceEvent {
  id: number
  case_id: string
  t: string
  kind: TraceKind
  agent?: AgentName | null
  detail?: string | null
  latency_ms?: number | null
  output?: Record<string, unknown> | null
}

export interface L2StreamEvent extends TraceEvent {
  state: CaseState
  category: Category | null
  is_safety: boolean
}

export interface Persona {
  id: string
  role: Role
  display_name: string
  rating: number | null
  dispute_count_30d: number
  trips: number
  scenario_trips: number
  awaiting_my_response: number
}

export interface Trip {
  id: string
  scheduled_at: string | null
  completed_at: string | null
  scenario_hint: string | null
  my_role: Role
  other_party_id: string
  other_party_name: string
  total_fare: number | null
  add_on_fees: { type: string; amount: number }[] | null
  case_id: string | null
  case_state: CaseState | null
  claimable: boolean
}

export interface CaseSummary {
  id: string
  state: CaseState
  category: Category | null
  trip_id: string
  created_at: string
  updated_at: string
  my_side: 'complainer' | 'complainee'
  other_party_id: string
  other_party_name: string
  needs_my_response: boolean
}

export interface CaseView {
  id: string
  trip_id: string
  state: CaseState
  category: Category | null
  tier: string | null
  is_safety: boolean
  claim_text: string | null
  created_at: string
  updated_at: string
  complainer_id: string
  complainer_name: string
  complainer_role: Role
  complainee_id: string
  complainee_name: string
  response: { text: string; submitted_at: string } | null
}

export interface RecentCase {
  id: string
  state: CaseState
  category: Category | null
  created_at: string
  updated_at: string
  complainer_name: string
  complainer_role: Role
  complainee_name: string
}

export interface DecisionResponse {
  case_id: string
  state: CaseState
  decision: DecisionObject
  document: string
}

export interface L2QueueItem {
  id: string
  state: CaseState
  category: Category | null
  tier: string | null
  is_safety: boolean
  created_at: string
  updated_at: string
  claim_text: string | null
  complainer_name: string
  complainer_role: Role
  complainee_name: string
  outcome: string | null
  remedy: Remedy | null
  confidence: number | null
  escalation: Escalation | null
  policy_applied: string | null
}

export interface EvidenceRef {
  kind: string
  hash: string
  object_key: string
}

export interface Accepted {
  case_id: string
  state: string
  events: string
}

export interface Stats {
  cases: number
  by_state: Partial<Record<CaseState, number>>
  by_category: Partial<Record<Category, number>>
  decided_automatically: number
  decided_by_human: number
  awaiting_human: number
  median_seconds_to_decision: number | null
  escalation_reasons: Record<string, number>
  trips: number
  users: number
}

export interface EvidenceItem {
  kind:
    | 'chat_message'
    | 'photo'
    | 'traffic_event'
    | 'payment'
    | 'gps_trace'
    | 'behavior_profile'
    | 'pickup_proximity'
    | 'route'
    | 'route_comparison'
  data: any // eslint-disable-line @typescript-eslint/no-explicit-any -- shape depends on kind
}

export type EvidenceIndex = Record<string, EvidenceItem>

export interface DemoScenario {
  trip_id: string
  user_id: string
  display_name: string
  other_party_name: string
  role: Role
  category: Category
}

export type DamageTier = 'none' | 'minor' | 'moderate' | 'severe' | 'unclear'

export interface DamageFinding {
  shows_vehicle_interior: boolean
  mess_type: string
  extent: 'small' | 'medium' | 'large'
  description: string
  confidence: number
  tier: DamageTier
}
