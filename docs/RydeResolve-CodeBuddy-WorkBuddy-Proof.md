# RydeResolve — CodeBuddy / WorkBuddy Usage and Proof

**Owner:** Dev B (@shiv0112)
**Why this matters:** the handbook makes it a hard gate. Every project must be built on at least one of CodeBuddy or WorkBuddy, with proof of usage, or it doesn't proceed to scoring. The submission form asks for chat history (at least 3 screenshots) or API call logs, and a one-paragraph "how we used CodeBuddy/WorkBuddy and what it was like".
**Status:** nothing captured yet. Start today; screenshots taken during real work are much more convincing than ones reconstructed at the end.

---

## The rule we're following

Do **real, useful work** in CodeBuddy and WorkBuddy, then screenshot and export that work. Don't stage re-creations of code that was already written elsewhere and present them as how it was built. Judges can compare the timestamps in the screenshots with our git history. The tasks below are all things the project actually still needs, chosen so they don't collide with what @suryaansh2002 is working on (the frontend and execution-plan step 5: Image Analysis, golden-run, prompt tuning).

## 1. Setup (about 15 minutes)

1. Go to **[codebuddy.ai](https://codebuddy.ai)**, the international site (not copilot.tencent.com, which is the China product). Sign up with the **same email you used for hackathon registration**: the handbook asks for one email across every registration page, and the credits are tied to it.
2. Redeem the hackathon credit code (it covers both CodeBuddy and WorkBuddy) under your avatar → Profile / Usage Management.
3. Install the **CodeBuddy IDE** (desktop) or the **CodeBuddy plugin for VS Code**. Optionally also install the CLI (`npm i -g @tencent-ai/codebuddy-code`, Node 18+). Its `/stats` and `/export` commands are the cleanest "API call log" proof.
4. Install **WorkBuddy** from [workbuddy.ai](https://www.workbuddy.ai), signed in with the same account.
5. Clone the repo, create a branch per task (`dev-b/<task>`), and open it in CodeBuddy. Read the docs in `docs/` first; CodeBuddy can be pointed at them as context too.

CodeBuddy has two modes worth using: **Ask** (questions, explanations, reviews; doesn't edit files) and **Craft** (an agent that plans and edits code). Use Craft for the coding tasks below.

## 2. Coding tasks to do in CodeBuddy (Craft mode)

Each is small, self-contained, needs no Groq calls in its tests, and is useful to the project. Open a PR per task; CI runs `pytest` and `ruff` automatically.

### Task A — Safety-language backstop for Prevention Rule 3 (most valuable)
The Policy doc lists this as an open item: Rule 3's safety hard-stop relies only on the Triage Agent's `is_safety` flag, and the "safety keyword/regex list … isn't drafted". Add a deterministic backstop, so that if the model misses obvious safety language, the claim is still routed to a human.
- In `backend/app/rules/prevention.py`, add a keyword/regex list (assault, threat, weapon, knife, unsafe driving, drunk, harass, grabbed, followed me, police, 995, and so on) and an `is_safety_language(text)` function. Keep it plain Python, with no model calls (deterministic rules, not an agent).
- Wire it in so that `PreventionContext` treats the claim as safety if *either* Triage says so *or* the keyword check fires. That needs the claim text passed in from `backend/app/orchestrator/pipeline.py` (`process_claim`). Record which signal fired in the trace detail.
- Tests in `backend/tests/test_prevention.py`: true positives, near-misses that should *not* fire ("unsafe" in "the app said the route was unsafe for bikes"?), and the either-signal logic.
- Label the list in a comment as **our own design choice, not Ryde-sourced** (the Policy doc's rule about labelling invented figures).

### Task B — Tests for the synthetic data pipeline
`backend/data_generation/pipeline/` has no unit tests. Add `backend/tests/test_data_generation.py` covering:
- `geo.py`: `haversine_km` on a known pair; `interpolate_gps_trace` returns points from start to end in time order; `perturb_route` makes a route longer.
- `fares.py`: platform fee is $1.25 at or below $18 and $1.47 above (real Ryde figures); `apply_no_show_fee` adds exactly $4.50.
- `chat.py`: a property damage claim's text matches its severity (spill → minor, mud → moderate, vomit → severe).
- `golden_cases.py`: the oracle functions (`_route_deviation_outcome`, `_no_show_outcome`, `_property_damage_outcome`) at their tier boundaries.

None of these need the database or the network; keep it that way.

### Task C — Ask-mode code review (quick, good screenshots)
In **Ask** mode, have CodeBuddy explain and critique one piece of the system: for example `backend/app/rules/escalation.py` plus `backend/app/rules/compliance.py` ("Can a decision ever skip the escalation gate? Can the compliance check ever author a decision?"). If it finds anything real, open an issue or a fix PR. This shows CodeBuddy being used to understand and verify the agentic architecture, not just to write code.

## 3. Non-code tasks for WorkBuddy (and Miora)

These are submission deliverables we need anyway.

- **WorkBuddy: draft the submission copy.** Give it `README.md`, `docs/RydeResolve-System-Design.md` and `docs/RydeResolve-Execution-Plan.md`, and ask for:
  - the project title,
  - the under-10-word blurb,
  - the project description (overview, real-world insight, solution design, business value),
  - the social media post.

  Edit the results and save the final versions to `submission/copy.md`.
- **WorkBuddy: demo video outline.** Ask for a 5–8 minute script structured problem → solution → live demo → impact, using the live app's flow: landing → file a claim → watch the agents argue → decision → L2 review. Save to `submission/demo-script.md`.
- **Miora (optional): the 16:9 cover image** the form requires. Prompt it with the product idea (two advocates, one judge, a ride route), with no Ryde logo or real brand marks. Save to `submission/cover.png`.
- **WorkBuddy as a task board (optional):** track the execution-plan steps there, and screenshot the board as tasks move.

## 4. What to capture, and where it goes

Put everything in `submission/proof/` in the repo (screenshots are fine to commit; **never** commit anything showing an API key or the `.env`).

| # | Capture | How |
|---|---|---|
| 1 | CodeBuddy chat for Task A, showing the Craft plan and code diff | screenshot during the session |
| 2 | CodeBuddy chat for Task B | screenshot |
| 3 | CodeBuddy Ask-mode review (Task C) | screenshot |
| 4 | CodeBuddy **History** panel listing all the sessions | History button, top right of the chat sidebar |
| 5 | Each conversation **exported** | History → Export, or `/export` in the CLI |
| 6 | Credits usage page (proof of real API use) | avatar → Profile / Usage Management |
| 7 | CLI `/stats` and `/cost` output, if you used the CLI | screenshot |
| 8 | WorkBuddy task(s) producing the submission copy and demo script | screenshot of the task and its output |
| 9 | Miora cover-image session, if used | screenshot |

That's well over the minimum of 3 screenshots, from more than one tool, which makes the strongest case.

## 5. The one-paragraph write-up

The form asks how we used CodeBuddy/WorkBuddy and what it was like. Write it from what actually happened in your sessions. It should be specific and honest: which tasks, which mode, what worked, what you had to correct. Save it to `submission/product-sharing.md`. Don't claim CodeBuddy built parts of the system it didn't. Say plainly that development used several AI coding assistants, and describe what CodeBuddy and WorkBuddy did.

## Done checklist

- [ ] Signed in on codebuddy.ai and workbuddy.ai with the registration email; credits redeemed
- [ ] Task A merged (safety-language backstop + tests)
- [ ] Task B merged (data-pipeline tests)
- [ ] Task C review done (and any finding filed)
- [ ] WorkBuddy drafts saved: `submission/copy.md`, `submission/demo-script.md`
- [ ] Cover image saved (`submission/cover.png`)
- [ ] All screenshots and exports in `submission/proof/` (none showing secrets)
- [ ] `submission/product-sharing.md` written
