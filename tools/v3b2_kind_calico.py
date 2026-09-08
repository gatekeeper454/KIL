#!/usr/bin/env python3
"""Run the closed V3B-2a Kind/Calico lifecycle."""

from __future__ import annotations

from argparse import ArgumentParser
import json
from pathlib import Path
import sys

from kil.v3b2_controller import (
    ControllerError,
    ControllerPaths,
    SubprocessCommandRunner,
    V3B2Controller,
)
from kil.v3b2_evidence import EvidenceError, verify_bundle
from kil.v3b2_journal import JournalError


ROOT = Path(__file__).resolve().parents[1]


def make_parser() -> ArgumentParser:
    parser = ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "up", "request-free", "nominal", "down", "recover"):
        subparsers.add_parser(name)
    view = subparsers.add_parser("view")
    view.add_argument("--bundle", required=True, type=Path)
    return parser


def _paths() -> ControllerPaths:
    return ControllerPaths(
        repository=ROOT,
        profile=ROOT / "deploy/kind/v3b2-profile.json",
        tools=ROOT / ".tools/bin",
        private=ROOT / ".tools/v3b2-private",
        public=ROOT / "artifacts/generated/v3b2-kind-calico",
    )


def _project(value: object) -> object:
    if hasattr(value, "result_tuple"):
        return {
            "run_id": value.run_id,
            "result_tuple": value.result_tuple,
            "instructions_sent": value.instructions_sent,
            "owned_teardown": value.owned_teardown,
            "bundle": value.bundle,
            "public_commitment": value.public_commitment,
        }
    return value


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        if args.command == "view":
            verified = verify_bundle(args.bundle.resolve())
            result = {
                "run_id": verified.run_id,
                "result_class": verified.result_class,
                "promotion_status": verified.promotion_status,
                "public_commitment": verified.public_commitment,
            }
        else:
            paths = _paths()
            controller = V3B2Controller(paths, SubprocessCommandRunner(paths.repository, paths.tools))
            method = getattr(controller, args.command.replace("-", "_"))
            result = _project(method())
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (ControllerError, EvidenceError, JournalError) as error:
        code = str(error)
        if not code.replace("_", "").isalnum() or len(code) > 64:
            code = "closed_failure"
        print(f"v3b2_error:{code}", file=sys.stderr)
        return 2
    except Exception:
        print("v3b2_error:closed_failure", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
