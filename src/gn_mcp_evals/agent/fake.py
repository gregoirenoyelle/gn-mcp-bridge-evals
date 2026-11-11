"""A scripted model: calls the given tools in order, no API. For tests and for checking cases on the site."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gn_mcp_evals.agent.model import ToolCall, Toolbox, Transcript


@dataclass(frozen=True)
class Step:
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)


class FakeModel:
    """Runs `steps` one per turn, whatever the tools return, then ends with `final_text`."""

    name = "fake"

    def __init__(self, steps: list[Step], final_text: str = "Done.") -> None:
        self._steps = steps
        self._final_text = final_text

    async def run(self, instruction: str, toolbox: Toolbox) -> Transcript:
        transcript = Transcript()
        for step in self._steps:
            outcome = await toolbox.call(step.tool, step.arguments)
            transcript.tool_calls.append(ToolCall(step.tool, step.arguments, outcome))
            transcript.turns += 1
        transcript.turns += 1
        transcript.final_text = self._final_text
        transcript.stop_reason = "end_turn"
        return transcript
