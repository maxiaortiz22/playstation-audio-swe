"""Canonical M1 stimulus and explicit baseline commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .artifacts import write_stimulus_package
from .baselines import create_approved_baseline, replace_approved_baseline
from .contracts import load_contract
from .stimuli import generate_stimulus


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
    create = commands.add_parser("baseline-create", help="explicitly approve generation one")
    _approval_arguments(create)
    create.add_argument("--baseline-id", required=True)
    replace = commands.add_parser("baseline-replace", help="explicitly approve a replacement")
    _approval_arguments(replace)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
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
