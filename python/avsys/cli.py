"""Canonical M1 stimulus and explicit baseline commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .analysis import AlignmentPolicyError, AnalysisInputError
from .artifacts import write_stimulus_package
from .baselines import create_approved_baseline, replace_approved_baseline
from .contracts import ContractError, load_contract
from .faults import FaultParameterError
from .stimuli import StimulusGenerationError, generate_stimulus
from .workflow import DemoInputError, run_workflow


def _approval_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--descriptor", required=True, type=Path)
    parser.add_argument("--environment-class", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--rationale", required=True)
    parser.add_argument("--approved-at", required=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="avsys")
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="write a deterministic stimulus package")
    generate.add_argument("--manifest", required=True, type=Path)
    generate.add_argument("--output", required=True, type=Path)
    run = commands.add_parser("run", help="execute the focused DEMO-3 workflow")
    run.add_argument("--manifest", required=True, type=Path)
    run.add_argument("--output", required=True, type=Path)
    create = commands.add_parser("baseline-create", help="explicitly approve generation one")
    _approval_arguments(create)
    create.add_argument("--baseline-id", required=True)
    replace = commands.add_parser("baseline-replace", help="explicitly approve a replacement")
    _approval_arguments(replace)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "run":
        try:
            outcome = run_workflow(args.manifest, args.output)
        except (
            AlignmentPolicyError,
            AnalysisInputError,
            ContractError,
            DemoInputError,
            FaultParameterError,
            FileNotFoundError,
            StimulusGenerationError,
        ) as error:
            print(f"avsys: invalid input or measurement: {error}", file=sys.stderr)
            return 2
        except Exception as error:  # runner/reporting failures retain exit meaning 3
            print(f"avsys: internal runner/reporting error: {error}", file=sys.stderr)
            return 3
        print(
            json.dumps(
                {
                    "output_directory": str(Path(args.output)),
                    "report": str(outcome.report_path),
                    "result": str(outcome.result_path),
                    "run_status": outcome.result["run_status"],
                },
                sort_keys=True,
            )
        )
        return outcome.exit_code

    if args.command == "generate":
        package = write_stimulus_package(args.manifest, args.output)
        print(
            json.dumps(
                {
                    "manifest_sha256": package.manifest_sha256,
                    "pcm_sha256": package.pcm_sha256,
                    "output_directory": str(package.directory),
                },
                sort_keys=True,
            )
        )
        return 0

    manifest = load_contract(args.manifest, contract="manifest")
    stimulus = generate_stimulus(manifest)
    common = {
        "manifest": manifest,
        "stimulus": stimulus,
        "environment_class": args.environment_class,
        "reviewer": args.reviewer,
        "rationale": args.rationale,
        "approved_at": args.approved_at,
    }
    if args.command == "baseline-create":
        descriptor = create_approved_baseline(
            args.descriptor, baseline_id=args.baseline_id, **common
        )
    else:
        descriptor = replace_approved_baseline(args.descriptor, **common)
    print(
        json.dumps(
            {
                "baseline_id": descriptor["baseline_id"],
                "generation": descriptor["generation"],
                "pcm_sha256": descriptor["pcm"]["sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


__all__ = ["main"]
