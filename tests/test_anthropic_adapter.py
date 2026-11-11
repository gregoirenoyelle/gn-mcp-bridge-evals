"""Anthropic adapter loop, tested against a scripted fake client: no API call, no site."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("anthropic")  # optional `agent` extra: layer 1 CI does not install it

from gn_mcp_evals.agent.__main__ import main  # noqa: E402
from gn_mcp_evals.agent.anthropic_adapter import (  # noqa: E402
    API_KEY_VARIABLE,
    MAX_TURNS_STOP,
    AnthropicModel,
    MissingApiKey,
    tool_params,
)
from gn_mcp_evals.agent.model import ToolDefinition, ToolOutcome, Usage  # noqa: E402

pytestmark = pytest.mark.anyio


def text(value: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=value)


def tool_use(block_id: str, name: str, arguments: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=arguments)


def response(stop_reason: str, *content: SimpleNamespace, cache_read: int | None = None) -> SimpleNamespace:
    usage = SimpleNamespace(
        input_tokens=100, output_tokens=10, cache_creation_input_tokens=None, cache_read_input_tokens=cache_read
    )
    return SimpleNamespace(stop_reason=stop_reason, content=list(content), usage=usage)


class ScriptedClient:
    """Returns the given responses in order and records each request."""

    def __init__(self, *responses: SimpleNamespace) -> None:
        self._responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.messages = self

    async def create(self, **params: Any) -> SimpleNamespace:
        self.requests.append(params)
        return self._responses.pop(0)


class RecordingToolbox:
    def __init__(self, refuse: frozenset[str] = frozenset()) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.refuse = refuse

    @property
    def definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition("gn-mcp-get-post", "Read a post", {"type": "object"}),
            ToolDefinition("gn-mcp-create-post", "Create a post", {"type": "object"}),
        ]

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        self.calls.append((name, arguments))
        if name in self.refuse:
            return ToolOutcome("Sorry, you are not allowed to do that.", is_error=True)
        return ToolOutcome('{"id": 7}')


async def test_runs_tools_until_end_turn_and_sums_usage() -> None:
    client = ScriptedClient(
        response("tool_use", text("Creating it."), tool_use("t1", "gn-mcp-create-post", {"title": "A"})),
        response("end_turn", text("Created post 7."), cache_read=50),
    )
    toolbox = RecordingToolbox()
    transcript = await AnthropicModel("claude-haiku-5-5", client=client).run("Create A", toolbox)

    assert toolbox.calls == [("gn-mcp-create-post", {"title": "A"})]
    assert transcript.stop_reason == "end_turn"
    assert transcript.final_text == "Created post 7."
    assert transcript.turns == 2
    assert transcript.usage == Usage(200, 20, 0, 50)
    # Second request: instruction, full assistant content, then one tool_result per tool_use.
    second = client.requests[1]["messages"]
    assert second[1]["content"][1].type == "tool_use"
    assert second[2] == {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "t1", "content": '{"id": 7}'}],
    }


async def test_site_refusal_goes_back_as_is_error() -> None:
    client = ScriptedClient(
        response("tool_use", tool_use("t1", "gn-mcp-get-post", {"id": 3}), tool_use("t2", "gn-mcp-create-post", {})),
        response("end_turn", text("I was not allowed to read post 3.")),
    )
    toolbox = RecordingToolbox(refuse=frozenset({"gn-mcp-get-post"}))
    transcript = await AnthropicModel("claude-haiku-5-5", client=client).run("Read 3", toolbox)

    results = client.requests[1]["messages"][2]["content"]
    assert [r["tool_use_id"] for r in results] == ["t1", "t2"]  # all results in one user message
    assert results[0]["is_error"] is True
    assert "is_error" not in results[1]
    assert transcript.tool_calls[0].outcome.is_error


async def test_turn_cap_stops_the_run() -> None:
    looping = [response("tool_use", tool_use(f"t{i}", "gn-mcp-get-post", {"id": i})) for i in range(5)]
    client = ScriptedClient(*looping)
    transcript = await AnthropicModel("claude-haiku-5-5", max_turns=3, client=client).run("Loop", RecordingToolbox())

    assert transcript.stop_reason == MAX_TURNS_STOP
    assert transcript.turns == 3
    assert len(client.requests) == 3


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
async def test_refusal_and_max_tokens_end_the_run(stop: str) -> None:
    client = ScriptedClient(response(stop))
    toolbox = RecordingToolbox()
    transcript = await AnthropicModel("claude-haiku-5-5", client=client).run("x", toolbox)

    assert transcript.stop_reason == stop
    assert toolbox.calls == []


async def test_pause_turn_continues() -> None:
    client = ScriptedClient(response("pause_turn", text("…")), response("end_turn", text("Done.")))
    transcript = await AnthropicModel("claude-haiku-5-5", client=client).run("x", RecordingToolbox())

    assert transcript.stop_reason == "end_turn"
    assert len(client.requests) == 2


async def test_request_shape() -> None:
    client = ScriptedClient(response("end_turn", text("ok")))
    await AnthropicModel("claude-haiku-5-5", effort="low", client=client).run("x", RecordingToolbox())

    request = client.requests[0]
    assert request["model"] == "claude-haiku-5-5"
    assert request["tool_choice"] == {"type": "auto"}
    assert request["output_config"] == {"effort": "low"}
    assert request["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert request["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in request["tools"][0]


async def test_no_effort_means_no_output_config() -> None:
    client = ScriptedClient(response("end_turn", text("ok")))
    await AnthropicModel("claude-haiku-5-5", client=client).run("x", RecordingToolbox())
    assert "output_config" not in client.requests[0]


def test_tool_params_without_tools() -> None:
    assert tool_params([]) == []


def test_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(API_KEY_VARIABLE, raising=False)
    with pytest.raises(MissingApiKey):
        AnthropicModel("claude-haiku-5-5")


def test_cli_exits_cleanly_without_api_key(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv(API_KEY_VARIABLE, raising=False)
    monkeypatch.setattr("gn_mcp_evals.agent.__main__.load_dotenv", lambda *a, **k: None)
    with pytest.raises(SystemExit) as exit_info:
        main(["--model", "claude-haiku-5-5", "--case", "create-post-full"])
    assert API_KEY_VARIABLE in str(exit_info.value.code)
