import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { EvidenceDrawer } from '../components/EvidenceDrawer'
import { api } from './api'
import type { EvidenceIndex } from '../types/api'

export type EvidenceView = 'operator' | 'party'

interface Ctx {
  caseId: string
  view: EvidenceView
  open: (ref: string) => void
  load: () => Promise<EvidenceIndex>
}

const EvidenceContext = createContext<Ctx | null>(null)

/** Wrap a case's page: any <Ref> inside opens the drawer with the cited item. */
export function EvidenceProvider({
  caseId,
  view,
  children,
}: {
  caseId: string
  view: EvidenceView
  children: ReactNode
}) {
  const [openRef, setOpenRef] = useState<string | null>(null)
  const cache = useRef<Promise<EvidenceIndex> | null>(null)
  const load = useCallback(() => {
    if (!cache.current) cache.current = api.evidence(caseId, view)
    return cache.current
  }, [caseId, view])
  const value = useMemo(() => ({ caseId, view, open: setOpenRef, load }), [caseId, view, load])
  return (
    <EvidenceContext.Provider value={value}>
      {children}
      {openRef && <EvidenceDrawer refId={openRef} onClose={() => setOpenRef(null)} />}
    </EvidenceContext.Provider>
  )
}

export function useEvidence(): Ctx | null {
  return useContext(EvidenceContext)
}

export function refKind(ref: string): string {
  if (ref.startsWith('MSG-')) return 'chat'
  if (ref.startsWith('EV-')) return 'photo'
  if (ref.startsWith('TRAFFIC-')) return 'traffic'
  if (ref.startsWith('POL-')) return 'policy'
  if (ref.startsWith('PROFILE-')) return 'history'
  if (ref === 'PAYMENT') return 'fare'
  if (ref === 'PICKUP-PROXIMITY') return 'gps'
  if (ref === 'GPS-TRACE') return 'gps'
  if (ref.startsWith('ROUTE-')) return 'route'
  return 'item'
}

/** A citation. Clickable when inside an EvidenceProvider. */
export function Ref({ id, stripped }: { id: string; stripped?: boolean }) {
  const ctx = useEvidence()
  const isPolicy = id.startsWith('POL-')
  if (stripped) {
    return (
      <span className="ref stripped" title="Not found in the case file. The validator removed this citation.">
        {id}
      </span>
    )
  }
  const hidden = ctx?.view === 'party' && id.startsWith('PROFILE-')
  if (!ctx || hidden) {
    return <span className={`ref${isPolicy ? ' policy' : ''}`}>{id}</span>
  }
  return (
    <button
      type="button"
      className={`ref${isPolicy ? ' policy' : ''}`}
      onClick={() => ctx.open(id)}
      title={`Open ${id}`}
    >
      <span className="ref-kind">{refKind(id)}</span>
      {id}
    </button>
  )
}
