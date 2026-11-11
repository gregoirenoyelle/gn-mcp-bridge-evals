"""Provider-neutral agent interface: what a model run returns, and the tools it is given.

Nothing here depends on a model provider: the fake model and the Anthropic adapter
both implement `AgentModel`, and the runner only knows this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Usage:
    """Token counts summed over the turns of a run (or over runs)."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_creation_input_tokens + other.cache_creation_input_tokens,
            self.cache_read_input_tokens + other.cache_read_input_tokens,
        )

    @property
    def total_input_tokens(self) -> int:
        """Uncached + cache writes + cache reads (all three are billed input)."""
        return self.input_tokens + self.cache_creation_input_tokens + self.cache_read_input_tokens


@dataclass(frozen=True)
class ToolDefinition:
    """A tool as offered to the model. Same shape as a Claude tool definition."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolOutcome:
    """What a tool call returned. A refusal by the site is `is_error=True`, never an exception."""

    text: str
    is_error: bool = False


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]
    outcome: ToolOutcome


@dataclass
class Transcript:
    """Everything a run produced. Recorded for the report, never used to score."""

    tool_calls: list[ToolCall] = field(default_factory=list)
    final_text: str = ""
    stop_reason: str = ""
    turns: int = 0
    usage: Usage = field(default_factory=Usage)
    messages: list[Any] = field(default_factory=list)


class Toolbox(Protocol):
    """The tools of one identity: their definitions, and a way to call them."""

    @property
    def definitions(self) -> list[ToolDefinition]: ...

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome: ...


class AgentModel(Protocol):
    """A model that runs an instruction to completion with the given tools."""

    @property
    def name(self) -> str: ...

    async def run(self, instruction: str, toolbox: Toolbox) -> Transcript: ...
