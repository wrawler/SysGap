"""Run the guided assessment, score-based catalog lookup, and consented upload."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Sequence


CLIENT_DIR = Path(__file__).resolve().parent
REPORT_DIR = CLIENT_DIR / "reports"
COMPONENTS = ("cpu", "gpu", "ram", "storage")


def _created_assessment(before: set[Path], report_dir: Path) -> Path:
    created = [
        path for path in report_dir.glob("assessment_*.json")
        if path.resolve() not in before
    ]
    if not created:
        raise RuntimeError("The collector finished without creating a new assessment JSON report.")
    return max(created, key=lambda path: path.stat().st_mtime_ns).resolve()


def _run(command: Sequence[str], label: str) -> int:
    print(f"\n  {label}")
    print("  " + "-" * 62)
    try:
        return subprocess.run(command, cwd=CLIENT_DIR, check=False).returncode
    except OSError as error:
        print(f"\n[ERROR] Could not start {label.lower()}: {error}", file=sys.stderr)
        return 1


def main() -> int:
    if sys.version_info < (3, 10):
        print("[ERROR] SysGap requires Python 3.10 or newer.", file=sys.stderr)
        return 1

    print(
        "\n"
        "  +------------------------------------------------------------+\n"
        "  |                         SYSGAP                             |\n"
        "  |       HARDWARE COLLECTION  >  PROFILE SCORING               |\n"
        "  |       CATALOG SHORTLIST    >  BACKEND SUBMISSION             |\n"
        "  +------------------------------------------------------------+\n"
        "  Assessment is local until you explicitly consent to upload.\n"
        "  No benchmark, stress test, or browser-based report is used.\n"
    )
    sample_answer = input(
        "  Include a 10-second ambient activity sample? [y/N]: "
    ).strip().casefold()

    try:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        before = {
            path.resolve()
            for path in REPORT_DIR.glob("assessment_*.json")
        }
    except OSError as error:
        print(f"[ERROR] Could not access the reports directory: {error}", file=sys.stderr)
        return 1

    print("\n  STEP 1 / 2   COLLECTION AND PROFILE SCORING")
    print("  Answer the guided questions; blank requirement fields use the")
    print("  selected profile's labeled planning floors when available.")
    collector_command = [
        sys.executable,
        str(CLIENT_DIR / "collector.py"),
        "--output-dir",
        str(REPORT_DIR),
    ]
    if sample_answer in {"y", "yes"}:
        collector_command.extend(["--sample-seconds", "10"])
    collection_status = _run(collector_command, "Collecting and scoring this PC")
    if collection_status != 0:
        return collection_status

    try:
        report_path = _created_assessment(before, REPORT_DIR)
    except (OSError, RuntimeError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1

    print("\n  STEP 2 / 2   SCORE-BASED CATALOG LOOKUP AND REPORT")
    print("  Each component score is checked separately; catalog options are")
    print("  requested only for components with a known gap.")
    comparison_command = [
        sys.executable,
        str(CLIENT_DIR / "compare_and_submit.py"),
        "--report",
        str(report_path),
        "--components",
        *COMPONENTS,
        "--upload",
    ]
    comparison_status = _run(
        comparison_command,
        "Finding closest passing specifications and preparing backend submission",
    )
    if comparison_status != 0:
        print(
            "\n[NOTICE] The local assessment is retained. Review the error above; "
            "catalog lookup or report submission did not complete.",
            file=sys.stderr,
        )
        return comparison_status

    print(f"\n  Local JSON/text reports: {REPORT_DIR}")
    print("  Completed. Any backend upload was made only after your consent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
