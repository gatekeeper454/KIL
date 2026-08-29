#!/usr/bin/env python3
"""Run the canonical KIL historical replay and emit a modeled bundle."""

from argparse import ArgumentParser
from decimal import Decimal
from pathlib import Path

from kil.domain import ReductionProfile
from kil.replay import replay
from kil.run_bundle import write_run_bundle
from kil.scenario import load_scenario


DEFAULT_SCENARIO = Path(
    "scenarios/hugging-face-july-2026/scenario-v1.json"
)
PROFILE_ID = "weighted-diagonal-v0-modeled"


def main() -> None:
    parser = ArgumentParser(
        description=(
            "Execute one deterministic KIL historical counterfactual replay. "
            "Every emitted decision remains modeled, not validated."
        )
    )
    parser.add_argument(
        "--scenario",
        type=Path,
        default=DEFAULT_SCENARIO,
        help=f"versioned scenario JSON (default: {DEFAULT_SCENARIO})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="parent directory for the content-addressed run bundle",
    )
    parser.add_argument(
        "--implementation-version",
        required=True,
        help="immutable source revision or build identity recorded in the bundle",
    )
    args = parser.parse_args()

    profile = ReductionProfile(Decimal("0.25"), Decimal("25"), 3)
    scenario = load_scenario(args.scenario)
    report = replay(scenario, profile)
    bundle = write_run_bundle(
        report,
        scenario,
        args.output,
        args.implementation_version,
        PROFILE_ID,
    )
    print(bundle)


if __name__ == "__main__":
    main()
