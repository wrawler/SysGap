"""Structured command-line entry point for the SysGap client."""

from __future__ import annotations

import argparse
from pathlib import Path

import diagnosis


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sysgap",
        description="Collect and assess hardware without benchmarks or stress tests.",
    )
    subparsers = parser.add_subparsers(dest="command")
    run = subparsers.add_parser(
        "run",
        help="Run the guided local assessment workflow.",
    )
    run.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "reports",
        help="Directory for local JSON/text reports.",
    )
    run.add_argument(
        "--sample-seconds",
        type=int,
        default=0,
        help="Optional passive sample duration, from 1 to 30 seconds.",
    )
    run.add_argument("--no-color", action="store_true", help="Disable styled terminal output.")
    run.add_argument("--verbose", action="store_true", help="Show technical collection details.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "run":
        build_parser().print_help()
        return 0
    return diagnosis.run_workflow(
        output_dir=args.output_dir,
        sample_seconds=args.sample_seconds,
        no_color=args.no_color,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    raise SystemExit(main())
