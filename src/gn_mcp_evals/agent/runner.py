"""Runs each case N times: setup -> model run -> check on the site -> cleanup.

Cleanup always runs, even when setup, the model or the check raises, so a failed
run never leaves posts or terms behind for the next one.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Literal

from gn_mcp_evals.agent.cases import Case, CaseContext
from gn_mcp_evals.agent.model import AgentModel, Toolbox, Transcript, Usage

Status = Literal["pass", "fail", "error"]

ModelFactory = Callable[[Case, CaseContext], AgentModel]
ToolboxFactory = Callable[[str], AbstractAsyncContextManager[Toolbox]]


@dataclass
class RunResult:
    case: Case
    run_index: int
    status: Status
    detail: str = ""
    transcript: Transcript = field(default_factory=Transcript)
    cleanup_error: str = ""

    @property
    def usage(self) -> Usage:
        return self.transcript.usage


def _describe(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"


async def run_once(
    case: Case,
    run_index: int,
    model_for: ModelFactory,
    toolbox_for: ToolboxFactory,
) -> RunResult:
    ctx = CaseContext()
    result = RunResult(case=case, run_index=run_index, status="error")
    try:
        case.setup(ctx)
        model = model_for(case, ctx)
        async with toolbox_for(case.identity) as toolbox:
            result.transcript = await model.run(case.render_instruction(ctx), toolbox)
        check = case.check(ctx)
        result.status = "pass" if check.passed else "fail"
        result.detail = check.detail
    except Exception as error:  # a broken run is reported, not raised: the other runs go on
        result.status = "error"
        result.detail = _describe(error)
    finally:
        try:
            case.cleanup(ctx)
        except Exception as error:
            result.cleanup_error = _describe(error)
    return result


async def run_cases(
    cases: list[Case],
    runs: int,
    model_for: ModelFactory,
    toolbox_for: ToolboxFactory,
    on_result: Callable[[RunResult], None] | None = None,
) -> list[RunResult]:
    """Every case `runs` times, sequentially (runs share one site)."""
    if runs < 1:
        raise ValueError("runs must be at least 1")
    results: list[RunResult] = []
    for case in cases:
        for run_index in range(1, runs + 1):
            result = await run_once(case, run_index, model_for, toolbox_for)
            results.append(result)
            if on_result:
                on_result(result)
    return results
