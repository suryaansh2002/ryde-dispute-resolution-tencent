"""Shared builder for the Rider and Driver Advocate agents (system design §6).

Both advocates are the same agent mirrored by role: identical `CaseFile` input,
identical tools (Evidence Lookup, Policy RAG; Image Analysis lands Day 6-7 once the
`DamageFinding` shape is frozen jointly), identical citation validator. Nothing
downstream branches on who filed — each argues its party's side either way.
"""

import json
from dataclasses import dataclass, field

from pydantic_ai import Agent, ModelRetry, RunContext

from app.config import settings
from app.schemas import Argument, CaseFile, CaseRole
from app.tools.evidence_lookup import evidence_index
from app.tools.policy_rag import search_policy

# Bad citations get this many correction attempts before being stripped and flagged
# (system design §4 rule 1) — each attempt is another Groq call.
CITATION_CORRECTION_ATTEMPTS = 1

# Kept out of the prompt body (potentially hundreds of points); fetched via evidence_lookup.
_HEAVY_FIELDS = {"gps_trace", "optimal_route_geometry", "actual_route_geometry"}


@dataclass
class AdvocateDeps:
    case_file: CaseFile
    role: CaseRole
    retrieved_policy_ids: set[str] = field(default_factory=set)
    stripped_cites: list[str] = field(default_factory=list)
    stripped_policy_cites: list[str] = field(default_factory=list)


@dataclass
class AdvocateRun:
    argument: Argument
    stripped_cites: list[str]
    stripped_policy_cites: list[str]

    @property
    def flagged(self) -> bool:
        """True when the validator had to strip citations — the orchestrator flags the case."""
        return bool(self.stripped_cites or self.stripped_policy_cites)


def _system_prompt(role: CaseRole) -> str:
    other = CaseRole.DRIVER if role == CaseRole.RIDER else CaseRole.RIDER
    return f"""\
You are the {role.title()} Advocate in RydeResolve, a ride-hailing dispute resolution system.
You argue the {role}'s side of this dispute — whether the {role} filed the claim or is
responding to it. An impartial Judge weighs your argument against the {other} advocate's,
built from the identical case file, under a policy that holds both parties to the same
evidentiary standard.

Rules:
- Ground every factual statement in the case file. List the ref ID of every evidence item
  you rely on in `cites`, using only IDs from "Citable evidence refs".
- Call policy_rag to find the clauses that govern this case. List every policy ID you rely
  on in `policy_cites`, using only IDs from the case file's policy_tags or returned by
  policy_rag in this run.
- Use evidence_lookup for GPS traces, route geometry and ROUTE-COMPARISON. Route distances
  are computed for you — never estimate distances or percentages yourself.
- State only what the case file or a tool result actually says, and describe each cited
  item accurately (e.g. read a behavior profile's numbers before characterizing it). If a
  policy test needs data the case file doesn't contain, say the test can't be applied —
  never infer the missing value.
- Advocate, don't fabricate: make the strongest honest case for the {role}. If the evidence
  cuts against the {role}, acknowledge it and lower your confidence rather than misstating
  it — the Judge sees the same evidence and discounts overreach.
- `confidence` (0.0-1.0): your honest estimate that the evidence supports the {role}'s
  position under policy.
- "Party statements", if present, are what each side *says* happened. They are claims to
  test against the evidence, not evidence themselves: they can't be cited in `cites`, and
  an unsupported statement doesn't outweigh the record.
- Refer to the parties as "the rider" and "the driver"; never assume anyone's gender.
- `role` is always "{role}". `text` is one paragraph of at most 120 words.
"""


@dataclass
class PartyStatements:
    """What each side says happened, in their own words — the complainer's claim and the
    complainee's response. Given to the advocates only, never to the Judge (system design
    §4 rule 2: the Judge never sees the original complaint text)."""

    complainer_role: CaseRole
    claim_text: str
    response_text: str | None = None

    def render(self) -> str:
        other = CaseRole.DRIVER if self.complainer_role == CaseRole.RIDER else CaseRole.RIDER
        response = self.response_text or "(no response submitted)"
        return (
            "Party statements (assertions to test against evidence, not citable):\n"
            f"- The {self.complainer_role} (who filed) says: {self.claim_text}\n"
            f"- The {other} (responding) says: {response}"
        )


def render_case_file(case_file: CaseFile) -> str:
    body = case_file.model_dump(mode="json", exclude=_HEAVY_FIELDS)
    refs = "\n".join(f"- {ref} ({item.kind})" for ref, item in evidence_index(case_file).items())
    return (
        f"Case file:\n{json.dumps(body, indent=2)}\n\n"
        f"Citable evidence refs (fetch any with evidence_lookup):\n{refs}"
    )


def build_advocate_agent(role: CaseRole) -> Agent[AdvocateDeps, Argument]:
    agent = Agent(
        settings.agent_model,
        output_type=Argument,
        deps_type=AdvocateDeps,
        system_prompt=_system_prompt(role),
        retries=2,
        name=f"{role}_advocate",
    )

    @agent.tool
    async def evidence_lookup(ctx: RunContext[AdvocateDeps], ref_id: str) -> dict | str:
        """Fetch the full contents of one evidence item in this case file by its ref ID."""
        index = evidence_index(ctx.deps.case_file)
        if ref_id not in index:
            return f"No evidence item {ref_id!r}. Valid refs: {', '.join(index)}"
        item = index[ref_id]
        return {"ref_id": ref_id, "kind": item.kind, "data": item.data}

    @agent.tool
    async def policy_rag(ctx: RunContext[AdvocateDeps], query: str) -> list[dict]:
        """Search the dispute resolution policy. Returns the most relevant clauses with
        their policy IDs, which you may then cite in `policy_cites`."""
        hits = search_policy(query)
        ctx.deps.retrieved_policy_ids.update(h.policy_id for h in hits)
        return [h.model_dump() for h in hits]

    @agent.output_validator
    async def validate_citations(ctx: RunContext[AdvocateDeps], out: Argument) -> Argument:
        deps = ctx.deps
        valid_refs = evidence_index(deps.case_file).keys()
        tagged = {t.policy_id for t in deps.case_file.policy_tags}
        valid_policies = tagged | deps.retrieved_policy_ids
        bad_cites = [c for c in out.cites if c not in valid_refs]
        bad_policies = [p for p in out.policy_cites if p not in valid_policies]
        bad_confidence = not 0.0 <= out.confidence <= 1.0

        if (bad_cites or bad_policies or bad_confidence) and ctx.retry < min(
            CITATION_CORRECTION_ATTEMPTS, ctx.max_retries
        ):
            problems = []
            if bad_cites:
                problems.append(
                    f"cites not in this case file: {bad_cites}; valid: {list(valid_refs)}")
            if bad_policies:
                problems.append(f"policy_cites never retrieved: {bad_policies}; "
                                f"valid: {sorted(valid_policies)} (or call policy_rag)")
            if bad_confidence:
                problems.append("confidence must be between 0.0 and 1.0")
            raise ModelRetry("Fix your argument: " + "; ".join(problems))

        deps.stripped_cites = bad_cites
        deps.stripped_policy_cites = bad_policies
        return out.model_copy(update={
            "role": deps.role,
            "cites": [c for c in out.cites if c in valid_refs],
            "policy_cites": [p for p in out.policy_cites if p in valid_policies],
            "confidence": min(max(out.confidence, 0.0), 1.0),
        })

    return agent


async def run_advocate(
    agent: Agent[AdvocateDeps, Argument],
    role: CaseRole,
    case_file: CaseFile,
    statements: PartyStatements | None = None,
) -> AdvocateRun:
    deps = AdvocateDeps(case_file=case_file, role=role)
    prompt = render_case_file(case_file)
    if statements is not None:
        prompt = f"{prompt}\n\n{statements.render()}"
    result = await agent.run(prompt, deps=deps)
    return AdvocateRun(result.output, deps.stripped_cites, deps.stripped_policy_cites)
