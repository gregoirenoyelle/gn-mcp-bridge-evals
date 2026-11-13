"""Command line: python -m gn_mcp_evals.agent --model <id|fake> [--runs N] [--case ID] [--identity NAME] [--out FILE] [--json FILE]

`--model fake` replays each case's scripted steps: no API call, used to check the
cases themselves against the site. Any other value is a Claude model id.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from gn_mcp_evals import site
from gn_mcp_evals.agent.cases import CASES, Case, CaseContext
from gn_mcp_evals.agent.fake import FakeModel
from gn_mcp_evals.agent.model import AgentModel
from gn_mcp_evals.agent.report import Meta, render, to_json
from gn_mcp_evals.agent.runner import ModelFactory, RunResult, run_cases
from gn_mcp_evals.agent.toolbox import mcp_toolbox

FAKE = "fake"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m gn_mcp_evals.agent", description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True, help=f"Claude model id, or '{FAKE}' for the scripted model")
    parser.add_argument("--runs", type=int, default=1, help="runs per case (default 1)")
    parser.add_argument("--case", action="append", default=[], help="only this case id (repeatable)")
    parser.add_argument("--identity", choices=["full", "drafts-only"], help="only cases for this identity")
    parser.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"], help="model effort level")
    parser.add_argument("--max-turns", type=int, default=20, help="turn cap per run (default 20)")
    parser.add_argument("--out", type=Path, help="write the report here (default: print it)")
    parser.add_argument("--json", type=Path, help="also write every run, with its full transcript, to this JSON file")
    args = parser.parse_args(argv)
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    return args


def select_cases(cases: list[Case], ids: list[str], identity: str | None) -> list[Case]:
    unknown = set(ids) - {case.id for case in cases}
    if unknown:
        raise SystemExit(f"Unknown case id: {', '.join(sorted(unknown))}")
    return [
        case for case in cases
        if (not ids or case.id in ids) and (identity is None or case.identity == identity)
    ]


def model_factory(args: argparse.Namespace) -> ModelFactory:
    if args.model == FAKE:
        return lambda case, ctx: FakeModel(case.fake_steps(ctx))
    try:
        from gn_mcp_evals.agent.anthropic_adapter import AnthropicModel, MissingApiKey
    except ImportError as error:
        raise SystemExit(f"Model '{args.model}' needs the Anthropic adapter: pip install -e '.[agent]' ({error})")
    try:
        model: AgentModel = AnthropicModel(args.model, effort=args.effort, max_turns=args.max_turns)
    except MissingApiKey as error:
        raise SystemExit(str(error)) from None

    def same_model(case: Case, ctx: CaseContext) -> AgentModel:
        return model

    return same_model


def progress(result: RunResult) -> None:
    print(f"{result.status:5} {result.case.id} #{result.run_index} {result.detail}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(find_dotenv(usecwd=True))
    args = parse_args(argv)
    cases = select_cases(CASES, args.case, args.identity)
    if not cases:
        print("No case selected.", file=sys.stderr)
        return 2
    model_for = model_factory(args)

    try:
        version = site.plugin_version()
    except RuntimeError as error:
        print(f"Could not read the gn-mcp-bridge version: {error}", file=sys.stderr)
        version = "unknown"

    results = asyncio.run(run_cases(cases, args.runs, model_for, mcp_toolbox, on_result=progress))
    meta = Meta(
        plugin_version=version,
        model=args.model,
        effort=args.effort or "default",
        runs_per_case=args.runs,
        date=datetime.date.today().isoformat(),
    )
    report = render(results, meta)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"Report written to {args.out}", file=sys.stderr)
    else:
        print(report)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(to_json(results, meta), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Runs written to {args.json}", file=sys.stderr)

    all_clean = all(result.status == "pass" and not result.cleanup_error for result in results)
    return 0 if all_clean else 1


if __name__ == "__main__":
    sys.exit(main())
