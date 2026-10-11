# frontend

React + Vite + TypeScript. One app with persona-scoped routes, not four separate apps (system design §3). There's no login, just a persona picker over the synthetic users.

| Route | View |
|---|---|
| `/` | Landing: the thesis, the pipeline drawn as a route line, one-click demo cases for all four categories, live numbers, persona picker |
| `/:role/:userId` | Rider/Driver panel: disputes waiting on you, your trips ("Report an issue"), your disputes |
| `/:role/:userId/file/:tripId` | Report a problem: category tiles, what gets checked automatically, photo drop zone. `?demo=1&category=…` pre-fills it, including a generated sample photo for damage |
| `/:role/:userId/case/:caseId` | Case: progress stepper, "what happens next", the decision as a ruling with clickable evidence, both sides' statements. Declined cases offer a refile |
| `/trace`, `/trace/:caseId` | System trace: live route line, stage captions, run metrics, both statements, then every agent output and gate |
| `/insights` | Accuracy: runs the 22 golden cases for real and shows the pass rate, per-category bars, label vs verdict per case (each links to its trace), and why cases went to a person |
| `/l2`, `/l2/:caseId` | Human review: queue table with "why a person" chips, the agents' recommendation, gate checks, ratify/override with structured reasons. Keys: J/K, A, O |

## Design

The system is impartial ink; only the two parties wear colour: rider blue, driver magenta, a pair validated colour-blind safe in both themes. Status colours (good, warning, critical) are reserved for outcomes and always come with a label. IBM Plex Sans, Plex Sans Condensed for labels and stations, Plex Mono for IDs, money and evidence refs. On the route line, agents are circles, deterministic rules are diamonds and the human step is a rounded square. Light, dark and system themes: tokens live in `src/index.css`, and the toggle is in the top bar.

- `src/types/api.ts`: hand-kept mirrors of the backend schemas
- `src/lib/api.ts`: REST client. Filing and responding use the backend's `?background=true` mode, so the UI gets the case id at once and watches the rest live.
- `src/lib/useEventStream.ts`: SSE hook; the backend replays history, then streams live, and `EventSource` resumes via `Last-Event-ID`
- `src/lib/pipeline.ts`: derives each station's state from the trace events (drives `RouteLine` and `StatusStepper`)
- `src/lib/evidence.tsx`: `EvidenceProvider` and `<Ref>`. Any citation opens `EvidenceDrawer` with the cited item: chat in context, a schematic map (`RouteMap`) of planned vs driven route, GPS fixes and the 100 m pickup radius, the fare, the photo, or the policy clause. The party view hides behaviour profiles
- `src/components/Ruling.tsx`: a decision as a ruling: outcome, remedy, cited findings, policy, confidence against the 0.6 threshold, "what would change this" (from policy thresholds, not the model), and `GateChecks`

## Running

```bash
npm install
npm run dev          # http://localhost:5173 — needs the backend on :8000
npm run build        # type-check + production build
npm run lint
```

Point at another backend with `VITE_API_URL` (see `.env.example`). It's read at build time, so set it in Vercel's project settings before building.

## Deploying (Vercel)

Project root `frontend/`, framework preset Vite, env var `VITE_API_URL=<the Render URL>`. `vercel.json` rewrites every path to `index.html`, so deep links like `/trace/CASE-0031` load.
