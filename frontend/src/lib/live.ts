import { useEffect, useMemo, useState } from 'react'
import type { CaseState, CaseView, DecisionResponse, EvidenceIndex, TraceEvent, UsageRow } from '../types/api'
import { api, streamUrl } from './api'
import { isFinal } from './format'
import { useApi } from './useApi'
import { useEventStream } from './useEventStream'

/** The state a case is in after its latest transition ("triage -> assembling"). */
export function stateFromEvents(events: TraceEvent[]): CaseState | undefined {
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i]
    if (e.kind === 'state_transition' && e.detail?.includes('->')) {
      return e.detail.split('->')[1].trim() as CaseState
    }
  }
  return undefined
}

export interface LiveCase {
  view: CaseView | undefined
  state: CaseState | undefined
  events: TraceEvent[]
  usage: UsageRow[]
  decision: DecisionResponse | undefined
  error: Error | undefined
  /** Still running: events arrive over SSE. */
  live: boolean
}

/**
 * Everything the hearing views need for one case. A finished case is fetched once; a
 * running one streams its trace over SSE (history first, then live) and refetches the
 * view, usage and decision as its state moves.
 */
export function useLiveCase(caseId: string | null): LiveCase {
  const [view, setView] = useState<CaseView>()
  const [error, setError] = useState<Error>()
  const [mode, setMode] = useState<'unknown' | 'live' | 'final'>('unknown')

  useEffect(() => {
    setView(undefined)
    setError(undefined)
    setMode('unknown')
    if (!caseId) return
    let on = true
    api.caseView(caseId).then(
      (v) => {
        if (!on) return
        setView(v)
        setMode(isFinal(v.state) ? 'final' : 'live')
      },
      (e: Error) => on && setError(e),
    )
    return () => {
      on = false
    }
  }, [caseId])

  const stream = useEventStream<TraceEvent>(caseId && mode === 'live' ? streamUrl.case(caseId) : null)
  const fixed = useApi(caseId && mode === 'final' ? `trace:${caseId}` : null, () => api.trace(caseId!))
  const events = useMemo(
    () => (mode === 'final' ? fixed.data ?? [] : stream.events),
    [mode, fixed.data, stream.events],
  )
  const state = stateFromEvents(events) ?? view?.state

  // The view carries the response text and names; refresh it when the state moves.
  useEffect(() => {
    if (!caseId || mode !== 'live' || !state || state === view?.state) return
    let on = true
    api.caseView(caseId).then((v) => on && setView(v), () => {})
    return () => {
      on = false
    }
  }, [caseId, mode, state, view?.state])

  const progress = events.filter((e) => e.kind === 'agent_output' || e.kind === 'tool_call').length
  const usage = useApi(caseId && progress ? `usage:${caseId}:${progress}` : null, () => api.usage(caseId!))
  const ruled = state === 'decided' || state === 'escalated'
  const reviews = events.filter((e) => e.kind === 'l2_review').length
  const decision = useApi(
    caseId && ruled && events.some((e) => e.agent === 'judge' || e.kind === 'l2_review')
      ? `decision:${caseId}:${state}:${reviews}`
      : null,
    () => api.decision(caseId!),
  )

  return {
    view,
    state,
    events,
    usage: usage.data ?? [],
    decision: decision.data,
    error: error ?? fixed.error,
    live: mode === 'live',
  }
}

/** The case file's evidence, keyed by the refs the agents cite. `version` refetches it
 * when the case file changes (assembly, then photo analysis). */
export function useEvidence(caseId: string | null, view: 'operator' | 'party' = 'operator', version = '') {
  return useApi<EvidenceIndex>(
    caseId ? `ev:${caseId}:${view}:${version}` : null,
    () => api.evidence(caseId!, view),
  )
}
