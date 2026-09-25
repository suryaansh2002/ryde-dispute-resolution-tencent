# RydeResolve — Development Roadmap (v1)

**Assumes:** 2 developers, ~14 calendar days, Claude Code used as a pair-programming force multiplier throughout (this also satisfies the mandatory CodeBuddy/WorkBuddy proof requirement — system design §8 — so proof capture is a running task, not a last-day scramble). Built directly against the three now-finalized documents: the System Design doc, the Policy & Prevention Rules doc (v3 — Part 1 reconciled against real Ryde figures), and the Data Sources & Strategy doc (v2 — finalized). Section references below point back to those.

---

## 0. Ownership split

Two developers, split by architecture layer rather than by feature, so each owns a coherent, independently testable slice.

| Owner | Owns | Source doc |
|---|---|---|
| **Dev A — "Agentic core"** | Orchestrator/state machine, Prevention Rules, Triage Agent, Evidence Collection Agent + its tools, Rider/Driver Advocates + their tools, Judge + its tools, the two-phase escalation gate, compliance check, decision-document rendering | System Design §4, §6 |
| **Dev B — "Data & product"** | Postgres schema + pgvector, R2, synthetic data generation pipeline, all four frontend panels, SSE client wiring, Logfire dashboard, deployment/infra, CodeBuddy/WorkBuddy proof capture | System Design §3, §5, §9; Data Sources doc |
| **Shared** | API contract and schemas (locked Day 1), demo video, submission checklist | System Design §7, §10 |

Both developers touch the API contract; nobody else touches the other's core files without a heads-up, to avoid merge conflicts in a two-week sprint.

---

## 1. Phasing overview

| Phase | Days | Goal |
|---|---|---|
| 1. Foundation | 1–2 | Repo, infra, schemas locked, Prevention Rules working standalone |
| 2. Core pipeline | 3–5 | Full baseline flow working end-to-end on at least one category |
| 3. Full roster + all categories | 6–8 | All three categories runnable; Image Analysis, observability, golden-case suite in place |
| 4. Frontend + polish | 9–10 | All four panels feature-complete; escalation bucket table decided and wired |
| 5. Hardening | 11 | Bug bash, full regression against golden cases |
| 6. Deployment + submission | 12–14 | Live, stable, demo recorded, submitted |

The single most important gate is the end of Phase 2 (Day 5): a claim going in one end and a decision document coming out the other, for real, on live infrastructure. If that slips, cut scope from Phase 3 (drop Image Analysis or one category) rather than compressing Phases 5–6 — a working three-category demo with weaker polish beats a broken five-agent one.

---

## 2. Day-by-day plan

| Day(s) | Dev A (agentic core) | Dev B (data & product) | Exit milestone |
|---|---|---|---|
| **1** | Stub orchestrator + state machine; empty agent files with typed signatures; Prevention Rules module skeleton + test harness | Stand up Neon (pgvector on), Vercel project, Render Docker skeleton; write initial migration for `cases`, `evidence`, `responses`, `decisions`, `trace_events` | **Joint first:** lock `CaseFile`, `Argument`, `DecisionObject`, `TriageResult`, and the API surface (system design §4, §7) before either dev writes real logic. Hello-world backend on Render + hello-world frontend on Vercel, both reachable |
| **2** | Implement all 6 Prevention Rules (Policy doc Part 2) with unit tests per rule, including the Triage-fed safety hard-stop; stub Triage Agent (`TriageResult` output, no real logic yet) | Add `users`, `trips`, `payments`, `chat_messages`, `traffic_events` tables (Data Sources doc §3); start `policy_chunks` ingestion from Policy doc Part 1 | A raw claim POSTed to `/cases` gets triaged and either hard-stopped or passed through — testable via API alone, no UI needed yet |
| **3–4** | Implement Evidence Collection Agent (assembles `CaseFile` via its DB Query / R2 Fetch / Policy RAG tools, with the output validator confirming every evidence reference resolves to a real Postgres row or R2 object — system design §4 rule 6); implement Rider + Driver Advocate agents with Evidence Lookup tool and the citation-validity output validator; stub Policy RAG tool against the now-ingested `policy_chunks` | Build the synthetic data generation pipeline steps 1–7 (Data Sources doc §4): trip population, OneMap routing, category assignment, route perturbation, traffic events, GPS trace, fare/payment generation; start Rider/Driver panel UI shells (claim filing, evidence upload) | Given one seeded trip, both advocates independently produce a policy-cited `Argument` from the identical `CaseFile` |
| **5** | Implement Judge agent (Policy RAG + Prevention-Rule Bucket + Escalate-to-L2 tools, `DecisionObject` schema + validator); implement the two-phase escalation gate as deterministic orchestrator code; implement `compliance_check()` and `render_decision_document()` | Implement the SSE broadcaster (`/events/cases/{id}`, `/events/l2`) and trace event bus; first version of the System Trace Panel rendering live `agent_output` cards | **Critical gate:** first full end-to-end run — claim → Triage → Prevention → Gatherer → Advocates → Judge → Escalation gate → decision document — on Route Deviation or No-Show (simpler than Property Damage since no photo evidence needed yet) |
| **6–7** | Implement the Image Analysis tool (vision call → `DamageFinding`) and wire it into the Property Damage path; harden output validators and retry behavior across all agents | Photo upload → R2 pipeline; generate/source the Property Damage photo set (Data Sources doc §4 steps 8–10); build the L2 console (queue view, ratification action) | All three categories runnable end-to-end; L2 console can view and ratify an escalated case |
| **8** | Add Logfire instrumentation (`logfire.configure()`, `instrument_pydantic_ai()`); verify tool-call spans show up correctly for both advocates and the Judge; build the `/golden-run` endpoint | Hand-label 30–50 golden cases across all three categories plus a few safety-flagged trips (Data Sources doc §4 step 11); build dashboard widgets (golden-case pass rate, throughput, category breakdown) | Logfire dashboard live with real spans; golden-case suite runs and reports a real pass-rate number |
| **9** | Decide and implement the evidence-disclosure-to-complainee behavior (system design §6.2 — still open; default to "outcome only, no evidence shown" as the more conservative choice unless decided otherwise, since it's easy to flip later given the payload is already server-driven) | Complete Rider/Driver panels (redacted view, decision document display) and Trace panel (readable argument cards); persona picker | Frontend feature-complete against all four views (system design §3) |
| **10** | Decide and wire the escalation bucket table contents (system design §6.1 — still open; start with a conservative default like "everything agent-decidable except anything already safety-flagged or fraud-flagged by Prevention Rule 5" and tune from there); re-check Prevention Rule 5's threshold now that it has no Fraud Agent backstop | CodeBuddy/WorkBuddy proof capture checkpoint; data quality pass on synthetic data (sanity-check GPS traces, fare consistency, photo-tier matching) | Escalation gate fully deterministic and tested on both phases independently |
| **11** | **Joint bug bash** — run the golden-case suite, manually test each category through the actual UI, fix what breaks | **Joint bug bash** — same day, paired testing; verify SSE reconnect behavior and that Render's free-tier spin-down doesn't break a judge's first click | No known critical bugs; golden-case pass rate recorded for submission materials |
| **12** | Production deployment double-check: env vars, secrets, Groq rate-limit headroom, error/fallback states | Draft submission form content (title, blurb, description) from the architecture docs; export the mermaid diagrams as the architecture-diagram deliverable; prepare cover image | Live URL stable and reachable exactly as a judge would hit it |
| **13** | **Joint** — record the demo video (5–8 min: overview, agent features, build-approach reflection) | **Joint** — same day; do a full dry run of the live demo end to end before recording locks in | Demo video recorded and edited |
| **14** | Final bug fixes only — no new features | Compile final CodeBuddy/WorkBuddy proof; verify GitHub repo is public/accessible; submit both the general form and the Ryde-track-specific deliverables (system design §10) | **Submitted** |

---

## 3. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Render free-tier backend spins down after 15 min idle, first click looks slow to a judge | An open SSE connection counts as activity (system design §9) — send a low-frequency keep-alive ping in the days before the demo, or warm it manually right before a judge is expected to click |
| Groq free-tier rate limits get hit during dev/testing, not just the real demo | Run the golden-case suite sparingly during development, add basic backoff/retry around agent calls early rather than after a limit is hit |
| pydantic-ai output-validator retries add latency/cost when a citation check fails | Budget for this from Day 3 — test the validator's retry path deliberately, don't assume happy-path timing |
| Two developers, no redundancy per component | A short daily sync (15 min) plus these three documents as the single source of truth — if one dev is blocked, the docs (not tribal knowledge) are enough for the other to unblock them |
| Escalation bucket table (§6.1) and evidence-disclosure decision (§6.2) are still genuinely undecided | Both get a stated conservative default in the Day 9–10 rows above, chosen specifically because they're cheap to change later — the goal is not blocking the schedule on a decision that isn't ready, not pretending the decision has been made |
| ~~Policy doc Part 1's numbers didn't match the real figures used in the Data Sources doc~~ — **resolved:** Part 1 has been reconciled to the real figures (Policy doc v3); no longer a Day 2 risk | Kept as a row, struck through, so it's visible that this was caught and closed rather than silently dropped from the list |

---

## 4. Definition of done (demo-ready checklist)

Pulled directly from system design §10, restated as a pre-submission gate:

- [ ] Working prototype, end-to-end, for all three in-scope categories (exceeds the two-category minimum)
- [ ] Architecture diagrams captured (already produced — system design §2, §4, §6)
- [ ] Demo walkthrough video recorded, showing a dispute processed and resolved autonomously
- [ ] Public/judge-accessible GitHub repository link
- [ ] CodeBuddy conversation history (min. 3 screenshots) and, if used, WorkBuddy board export
- [ ] Golden-case pass rate available as a real, computed number for the dashboard
- [ ] Live URL confirmed reachable from a cold start (not just from a machine that's been actively developing against it)
