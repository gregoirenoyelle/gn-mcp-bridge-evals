"""Markdown results report: success rate per ability and per identity, with what was tested."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from functools import reduce

from gn_mcp_evals.agent.model import Usage
from gn_mcp_evals.agent.runner import RunResult

EXCERPT_LENGTH = 300


@dataclass(frozen=True)
class Meta:
    plugin_version: str
    model: str
    effort: str
    runs_per_case: int
    date: str  # YYYY-MM-DD


def _rate(results: list[RunResult]) -> str:
    passed = sum(result.status == "pass" for result in results)
    errors = sum(result.status == "error" for result in results)
    rate = f"{passed}/{len(results)} ({100 * passed / len(results):.0f} %)"
    return f"{rate}, {errors} error{'s' if errors > 1 else ''}" if errors else rate


def _group(results: list[RunResult], key: Callable[[RunResult], Hashable]) -> dict[Hashable, list[RunResult]]:
    groups: dict[Hashable, list[RunResult]] = defaultdict(list)
    for result in results:
        groups[key(result)].append(result)
    return dict(sorted(groups.items()))


def _excerpt(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= EXCERPT_LENGTH else flat[:EXCERPT_LENGTH] + "…"


def render(results: list[RunResult], meta: Meta) -> str:
    usage = reduce(lambda total, result: total + result.usage, results, Usage())
    runs = len(results)
    lines = [
        f"# Agent evals — {meta.date}",
        "",
        f"- **gn-mcp-bridge version:** {meta.plugin_version}",
        f"- **Model:** `{meta.model}`",
        f"- **Effort:** {meta.effort}",
        f"- **Runs per case:** {meta.runs_per_case}",
        f"- **Overall:** {_rate(results)}" if results else "- **Overall:** no runs",
        "",
        "Pass or fail is read from the site state after each run, never from the model's answer.",
        "",
        "## Per ability",
        "",
        "| Ability | Identity | Kind | Passed |",
        "|---|---|---|---|",
    ]
    by_ability = _group(results, lambda r: (r.case.ability, r.case.identity, r.case.kind))
    for (ability, identity, kind), group in by_ability.items():
        lines.append(f"| `{ability}` | {identity} | {kind} | {_rate(group)} |")

    lines += ["", "## Per identity", "", "| Identity | Passed |", "|---|---|"]
    for identity, group in _group(results, lambda r: r.case.identity).items():
        lines.append(f"| {identity} | {_rate(group)} |")

    lines += [
        "",
        "## Token usage",
        "",
        "| | Total | Per run |",
        "|---|---|---|",
    ]
    rows = [
        ("Input, uncached", usage.input_tokens),
        ("Input, cache writes", usage.cache_creation_input_tokens),
        ("Input, cache reads", usage.cache_read_input_tokens),
        ("Output", usage.output_tokens),
    ]
    for label, total in rows:
        per_run = round(total / runs) if runs else 0
        lines.append(f"| {label} | {total:,} | {per_run:,} |")

    problems = [result for result in results if result.status != "pass" or result.cleanup_error]
    lines += ["", "## Failures and errors", ""]
    if not problems:
        lines.append("None.")
    for result in problems:
        transcript = result.transcript
        lines += [
            f"### `{result.case.id}`, run {result.run_index}: {result.status}",
            "",
            f"- **Detail:** {result.detail or '—'}",
            f"- **Stop reason:** {transcript.stop_reason or '—'}, {transcript.turns} turns, "
            f"{len(transcript.tool_calls)} tool calls",
        ]
        if transcript.tool_calls:
            calls = ", ".join(
                f"`{call.name}`{' (error)' if call.outcome.is_error else ''}" for call in transcript.tool_calls
            )
            lines.append(f"- **Tool calls:** {calls}")
        if transcript.final_text:
            lines.append(f"- **Final answer:** {_excerpt(transcript.final_text)}")
        if result.cleanup_error:
            lines.append(f"- **Cleanup error:** {result.cleanup_error}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
