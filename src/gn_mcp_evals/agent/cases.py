"""Eval cases: an instruction for one identity, plus setup, check and cleanup on the site.

`check` receives the case context only, never the transcript: pass or fail is
decided by the site state, not by what the model says it did.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from gn_mcp_evals.agent.fake import Step

Identity = Literal["full", "drafts-only"]
Kind = Literal["capability", "security"]


@dataclass
class CaseContext:
    """Per-run state. `marker` is unique to the run and goes in every title the case uses,
    so cleanup can find whatever the agent created."""

    marker: str = field(default_factory=lambda: f"evals-agent-{uuid.uuid4().hex[:8]}")
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Check:
    passed: bool
    detail: str = ""


def _nothing(ctx: CaseContext) -> None:
    return None


def _no_steps(ctx: CaseContext) -> list[Step]:
    return []


@dataclass(frozen=True)
class Case:
    id: str
    ability: str  # e.g. "gn-mcp/create-post"
    identity: Identity
    kind: Kind
    instruction: str  # formatted with `marker` and the keys of `ctx.data`
    check: Callable[[CaseContext], Check]
    setup: Callable[[CaseContext], None] = _nothing
    cleanup: Callable[[CaseContext], None] = _nothing
    fake_steps: Callable[[CaseContext], list[Step]] = _no_steps  # what a correct agent would do

    def render_instruction(self, ctx: CaseContext) -> str:
        return self.instruction.format(marker=ctx.marker, **ctx.data)


# Filled in Phase C.
CASES: list[Case] = []
