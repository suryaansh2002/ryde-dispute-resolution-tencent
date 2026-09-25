# frontend

React (Vite) + TypeScript, static bundle deployed on Vercel. One app, persona-scoped routes — not four separate apps. See `docs/RydeResolve-System-Design.md` §3.

- `src/routes/` — rider/:caseId, driver/:caseId, trace/:caseId, l2
- `src/components/` — shared UI (argument cards, decision document view, persona picker)
- `src/lib/` — REST client, SSE/EventSource wrapper
- `src/types/` — `CaseFile` / `Argument` / `DecisionObject` / `TriageResult` mirrors of the backend schemas
