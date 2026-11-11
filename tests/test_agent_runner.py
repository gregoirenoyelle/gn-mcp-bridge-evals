"""Agent-eval skeleton, tested with the fake model and fake tools: no site, no API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, TextContent, Tool

from gn_mcp_evals.agent.__main__ import parse_args, select_cases
from gn_mcp_evals.agent.cases import Case, CaseContext, Check
from gn_mcp_evals.agent.fake import FakeModel, Step
from gn_mcp_evals.agent.model import ToolDefinition, ToolOutcome, Transcript, Usage
from gn_mcp_evals.agent.report import Meta, render
from gn_mcp_evals.agent.runner import run_cases
from gn_mcp_evals.agent.toolbox import McpToolbox

pytestmark = pytest.mark.anyio


class FakeToolbox:
    """Records calls; tools listed in `refuse` answer with an error, like a site refusal."""

    def __init__(self, refuse: set[str] = frozenset()) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.refuse = refuse

    @property
    def definitions(self) -> list[ToolDefinition]:
        return [ToolDefinition("gn-mcp-create-post", "Create a post", {"type": "object"})]

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        self.calls.append((name, arguments))
        if name in self.refuse:
            return ToolOutcome("Sorry, you are not allowed to do that.", is_error=True)
        return ToolOutcome('{"id": 1}')


def toolbox_factory(toolbox: FakeToolbox, identities: list[str] | None = None):
    @asynccontextmanager
    async def factory(identity: str) -> AsyncIterator[FakeToolbox]:
        if identities is not None:
            identities.append(identity)
        yield toolbox

    return factory


def fake_model_for(case: Case, ctx: CaseContext) -> FakeModel:
    return FakeModel(case.fake_steps(ctx))


def make_case(**overrides: Any) -> Case:
    fields: dict[str, Any] = dict(
        id="create-post-full",
        ability="gn-mcp/create-post",
        identity="full",
        kind="capability",
        instruction="Create a draft titled {marker}.",
        check=lambda ctx: Check(True),
    )
    fields.update(overrides)
    return Case(**fields)


# --- fake model ---------------------------------------------------------------


async def test_fake_model_calls_steps_in_order_and_records_outcomes() -> None:
    toolbox = FakeToolbox(refuse={"gn-mcp-update-term"})
    model = FakeModel([Step("gn-mcp-create-post", {"title": "a"}), Step("gn-mcp-update-term", {"id": 3})])

    transcript = await model.run("do it", toolbox)

    assert toolbox.calls == [("gn-mcp-create-post", {"title": "a"}), ("gn-mcp-update-term", {"id": 3})]
    assert [call.outcome.is_error for call in transcript.tool_calls] == [False, True]
    assert transcript.stop_reason == "end_turn"
    assert transcript.turns == 3


# --- runner -------------------------------------------------------------------


async def test_runs_each_case_n_times_with_a_fresh_context() -> None:
    markers: list[str] = []
    case = make_case(check=lambda ctx: markers.append(ctx.marker) or Check(True))

    results = await run_cases([case], 3, fake_model_for, toolbox_factory(FakeToolbox()))

    assert [result.run_index for result in results] == [1, 2, 3]
    assert all(result.status == "pass" for result in results)
    assert len(set(markers)) == 3


async def test_failed_check_is_a_fail_with_its_detail() -> None:
    case = make_case(check=lambda ctx: Check(False, "post was published"))

    [result] = await run_cases([case], 1, fake_model_for, toolbox_factory(FakeToolbox()))

    assert result.status == "fail"
    assert result.detail == "post was published"


async def test_setup_data_reaches_instruction_and_fake_steps() -> None:
    seen: dict[str, Any] = {}

    def setup(ctx: CaseContext) -> None:
        ctx.data["post_id"] = 42

    class Recorder(FakeModel):
        async def run(self, instruction: str, toolbox: Any) -> Transcript:
            seen["instruction"] = instruction
            return await super().run(instruction, toolbox)

    case = make_case(
        instruction="Update post {post_id} ({marker}).",
        setup=setup,
        fake_steps=lambda ctx: [Step("gn-mcp-update-post", {"id": ctx.data["post_id"]})],
    )
    toolbox = FakeToolbox()
    identities: list[str] = []

    await run_cases([case], 1, lambda c, ctx: Recorder(c.fake_steps(ctx)), toolbox_factory(toolbox, identities))

    assert seen["instruction"].startswith("Update post 42 (evals-agent-")
    assert toolbox.calls == [("gn-mcp-update-post", {"id": 42})]
    assert identities == ["full"]


def _boom(ctx: CaseContext) -> None:
    raise RuntimeError("boom")


@pytest.mark.parametrize("stage", ["setup", "model", "check"])
async def test_cleanup_runs_when_a_stage_raises(stage: str) -> None:
    cleaned: list[str] = []

    class BrokenModel(FakeModel):
        async def run(self, instruction: str, toolbox: Any) -> Transcript:
            raise RuntimeError("boom")

    case = make_case(
        setup=_boom if stage == "setup" else (lambda ctx: None),
        check=_boom if stage == "check" else (lambda ctx: Check(True)),
        cleanup=lambda ctx: cleaned.append(ctx.marker),
    )
    model_for = (lambda c, ctx: BrokenModel([])) if stage == "model" else fake_model_for

    next_case = make_case(id="next", cleanup=lambda ctx: cleaned.append(ctx.marker))

    results = await run_cases([case, next_case], 1, model_for, toolbox_factory(FakeToolbox()))

    assert results[0].status == "error"
    assert results[0].detail == "RuntimeError: boom"
    assert len(results) == 2 and len(cleaned) == 2  # a broken run does not stop the suite


async def test_cleanup_error_is_recorded_without_hiding_the_result() -> None:
    case = make_case(cleanup=_boom)

    [result] = await run_cases([case], 1, fake_model_for, toolbox_factory(FakeToolbox()))

    assert result.status == "pass"
    assert result.cleanup_error == "RuntimeError: boom"


async def test_runs_must_be_positive() -> None:
    with pytest.raises(ValueError):
        await run_cases([make_case()], 0, fake_model_for, toolbox_factory(FakeToolbox()))


# --- MCP toolbox --------------------------------------------------------------


class FakeClient:
    def __init__(self, result: CallToolResult | None = None, error: MCPError | None = None) -> None:
        self.result, self.error = result, error

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        if self.error:
            raise self.error
        assert self.result is not None
        return self.result


TOOLS = [
    Tool(name="gn-mcp-create-post", description="Create a post", input_schema={"type": "object"}),
    Tool(name="gncom-get-portfolio", description="Theme tool", input_schema={"type": "object"}),
]


def test_toolbox_only_offers_the_plugin_tools() -> None:
    toolbox = McpToolbox(FakeClient(), TOOLS)  # type: ignore[arg-type]

    assert [definition.name for definition in toolbox.definitions] == ["gn-mcp-create-post"]
    assert toolbox.definitions[0].input_schema == {"type": "object"}


async def test_toolbox_turns_refusals_into_error_outcomes() -> None:
    error_result = CallToolResult(content=[TextContent(type="text", text="not allowed")], is_error=True)
    from_result = await McpToolbox(FakeClient(result=error_result), TOOLS).call("gn-mcp-create-post", {})  # type: ignore[arg-type]
    from_exception = await McpToolbox(FakeClient(error=MCPError(-32000, "forbidden")), TOOLS).call(  # type: ignore[arg-type]
        "gn-mcp-create-post", {}
    )
    unknown = await McpToolbox(FakeClient(), TOOLS).call("gncom-get-portfolio", {})  # type: ignore[arg-type]

    assert from_result == ToolOutcome("not allowed", is_error=True)
    assert from_exception.is_error and "forbidden" in from_exception.text
    assert unknown.is_error


# --- report -------------------------------------------------------------------


async def test_report_gives_rates_per_ability_and_identity_with_version_and_tokens() -> None:
    class Spending(FakeModel):
        async def run(self, instruction: str, toolbox: Any) -> Transcript:
            transcript = await super().run(instruction, toolbox)
            transcript.usage = Usage(input_tokens=100, output_tokens=10, cache_read_input_tokens=1000)
            return transcript

    outcomes = iter([True, False])
    cases = [
        make_case(check=lambda ctx: Check(next(outcomes), "draft missing")),
        make_case(id="publish-drafts-only", identity="drafts-only", kind="security"),
    ]
    results = await run_cases(cases, 2, lambda c, ctx: Spending([]), toolbox_factory(FakeToolbox()))

    report = render(results, Meta("1.8.2", "claude-haiku-5-5", "low", 2, "2026-11-11"))

    assert "**gn-mcp-bridge version:** 1.8.2" in report
    assert "`claude-haiku-5-5`" in report
    assert "| `gn-mcp/create-post` | full | capability | 1/2 (50 %) |" in report
    assert "| `gn-mcp/create-post` | drafts-only | security | 2/2 (100 %) |" in report
    assert "| full | 1/2 (50 %) |" in report
    assert "| Input, cache reads | 4,000 | 1,000 |" in report
    assert "### `create-post-full`, run 2: fail" in report
    assert "draft missing" in report


# --- command line -------------------------------------------------------------


def test_select_cases_filters_by_id_and_identity() -> None:
    cases = [make_case(), make_case(id="publish-drafts-only", identity="drafts-only")]

    assert [c.id for c in select_cases(cases, [], "drafts-only")] == ["publish-drafts-only"]
    assert [c.id for c in select_cases(cases, ["create-post-full"], None)] == ["create-post-full"]
    with pytest.raises(SystemExit):
        select_cases(cases, ["nope"], None)


def test_model_is_required_and_runs_positive() -> None:
    with pytest.raises(SystemExit):
        parse_args([])
    with pytest.raises(SystemExit):
        parse_args(["--model", "fake", "--runs", "0"])
    assert parse_args(["--model", "fake", "--runs", "3"]).runs == 3
