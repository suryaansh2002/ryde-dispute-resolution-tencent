import type {
  Accepted,
  CaseSummary,
  CaseView,
  Category,
  DecisionObject,
  DecisionResponse,
  DemoScenario,
  EvidenceIndex,
  EvidenceRef,
  L2QueueItem,
  Outcome,
  Persona,
  PolicyTag,
  RecentCase,
  Stats,
  Remedy,
  Role,
  Trip,
} from '../types/api'

export const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, init)
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') message = body.detail
      else if (body.detail) message = JSON.stringify(body.detail)
    } catch {
      // not JSON; keep the status line
    }
    throw new ApiError(res.status, message)
  }
  return res.json() as Promise<T>
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  health: (signal?: AbortSignal) => request<{ status: string }>('/health', { signal }),

  personas: (role: Role, limit = 40) =>
    request<Persona[]>(`/demo/personas?role=${role}&limit=${limit}`),
  trips: (userId: string) => request<Trip[]>(`/users/${userId}/trips`),
  userCases: (userId: string) => request<CaseSummary[]>(`/users/${userId}/cases`),

  stats: () => request<Stats>('/stats'),
  scenario: (category: Category) => request<DemoScenario>(`/demo/scenario?category=${category}`),
  evidence: (caseId: string, view: 'operator' | 'party') =>
    request<EvidenceIndex>(`/cases/${caseId}/evidence?view=${view}`),
  policy: (policyId: string) => request<PolicyTag[]>(`/policy/${policyId}`),
  recentCases: (limit = 30) => request<RecentCase[]>(`/cases?limit=${limit}`),
  caseView: (caseId: string) => request<CaseView>(`/cases/${caseId}/view`),
  decision: (caseId: string) => request<DecisionResponse>(`/cases/${caseId}/decision`),

  upload: (file: File, kind = 'photo') => {
    const form = new FormData()
    form.append('file', file)
    form.append('kind', kind)
    return request<EvidenceRef>('/uploads', { method: 'POST', body: form })
  },

  fileClaim: (body: {
    trip_id: string
    complainer_id: string
    category: Category
    claim_text: string
    evidence: EvidenceRef[]
  }) => request<Accepted>('/cases?background=true', json(body)),

  respond: (caseId: string, respondentId: string, text: string) =>
    request<Accepted>(
      `/cases/${caseId}/response?background=true`,
      json({ respondent_id: respondentId, text }),
    ),

  adjudicateNow: (caseId: string) =>
    request<unknown>(`/cases/${caseId}/adjudicate`, { method: 'POST' }),

  l2Queue: () => request<L2QueueItem[]>('/l2/queue'),
  l2Review: (
    caseId: string,
    body: {
      reviewer: string
      action: 'ratify' | 'override'
      note: string
      outcome?: Outcome
      remedy?: Remedy
    },
  ) => request<DecisionObject>(`/l2/cases/${caseId}/ratify`, json(body)),
}

export const streamUrl = {
  case: (caseId: string) => `${API_URL}/events/cases/${caseId}`,
  l2: () => `${API_URL}/events/l2`,
}

export const evidenceContentUrl = (evidenceId: string) => `${API_URL}/evidence/${evidenceId}/content`

export const samplePhotoUrl = (tier: 'none' | 'minor' | 'moderate' | 'severe', seed = 0) =>
  `${API_URL}/demo/sample-photo?tier=${tier}&seed=${seed}`
