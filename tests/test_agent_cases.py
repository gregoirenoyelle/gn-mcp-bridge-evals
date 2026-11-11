"""Agent eval cases, checked against the site with scripted models: no API call.

For every case:
- a correct agent (the case's fake steps) passes, and cleanup leaves nothing behind;
- the check is not vacuous: an agent that does nothing fails a capability case, and a
  security case fails once the forbidden change is made on the site through WP-CLI.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from gn_mcp_evals import site
from gn_mcp_evals.agent.cases import CASES, Case, CaseContext
from gn_mcp_evals.agent.fake import FakeModel
from gn_mcp_evals.agent.runner import RunResult, run_once
from gn_mcp_evals.agent.toolbox import mcp_toolbox
from gn_mcp_evals.client import Identity

pytestmark = pytest.mark.anyio

CAPABILITY = [case for case in CASES if case.kind == "capability"]
SECURITY = [case for case in CASES if case.kind == "security"]


def ids(cases: list[Case]) -> list[str]:
    return [case.id for case in cases]


async def run(case: Case, model_for: Callable[[Case, CaseContext], FakeModel]) -> tuple[RunResult, CaseContext]:
    seen: list[CaseContext] = []

    def recording(c: Case, ctx: CaseContext) -> FakeModel:
        seen.append(ctx)
        return model_for(c, ctx)

    result = await run_once(case, 1, recording, mcp_toolbox)
    assert seen, f"setup failed before the model ran: {result.detail}"
    return result, seen[0]


def assert_clean(result: RunResult, ctx: CaseContext) -> None:
    assert not result.cleanup_error, result.cleanup_error
    for text in [ctx.marker, *ctx.secrets]:
        assert site.find_containing(text) == [], f"posts left behind for {text}"
    for taxonomy in ("category", "post_tag"):
        assert site.find_terms_containing(ctx.marker, taxonomy) == [], f"{taxonomy} terms left behind"


def test_case_ids_are_unique() -> None:
    assert len(ids(CASES)) == len(set(ids(CASES)))


def test_every_security_case_has_a_breach() -> None:
    assert all(case.breach for case in SECURITY)


@pytest.mark.parametrize("case", CASES, ids=ids(CASES))
async def test_a_correct_agent_passes(case: Case, full_identity: Identity, drafts_only_identity: Identity) -> None:
    result, ctx = await run(case, lambda c, ctx: FakeModel(c.fake_steps(ctx)))

    assert result.status == "pass", f"{result.status}: {result.detail}"
    if case.kind == "security":
        refused = [call for call in result.transcript.tool_calls if call.outcome.is_error]
        assert refused, "the site did not refuse the scripted call: the case tests nothing"
    assert_clean(result, ctx)


@pytest.mark.parametrize("case", CAPABILITY, ids=ids(CAPABILITY))
async def test_an_idle_agent_fails(case: Case, full_identity: Identity, drafts_only_identity: Identity) -> None:
    result, ctx = await run(case, lambda c, ctx: FakeModel([]))

    assert result.status == "fail", f"{result.status}: {result.detail}"
    assert_clean(result, ctx)


@pytest.mark.parametrize("case", SECURITY, ids=ids(SECURITY))
async def test_a_breach_fails(case: Case, full_identity: Identity, drafts_only_identity: Identity) -> None:
    def breaching(c: Case, ctx: CaseContext) -> FakeModel:
        assert c.breach is not None
        c.breach(ctx)
        return FakeModel([])

    result, ctx = await run(case, breaching)

    assert result.status == "fail", f"{result.status}: {result.detail}"
    assert_clean(result, ctx)
