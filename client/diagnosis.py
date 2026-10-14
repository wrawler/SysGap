"""Run the guided assessment, score-based catalog lookup, and consented upload."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Sequence

from ui import console, header, phase


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


def _remove_intermediate_report(report_path: Path) -> None:
    """Remove the collection-only pair after a successful finalization."""
    for path in (report_path, report_path.with_suffix(".txt")):
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            raise RuntimeError(f"Could not remove intermediate report {path}: {error}") from error


def run_workflow(
    *,
    output_dir: Path | None = None,
    sample_seconds: int | None = None,
    no_color: bool = False,
    verbose: bool = False,
) -> int:
    output_dir = output_dir or REPORT_DIR
    output = console(no_color=no_color)
    if sys.version_info < (3, 10):
        output.print("[red]SysGap requires Python 3.10 or newer.[/red]", file=sys.stderr)
        return 1

    header(output)
    output.print("[dim]Local first. Catalog lookup and upload are separate optional steps.[/dim]")
    if sample_seconds is None:
        sample_answer = input(
            "  Include a 10-second ambient activity sample? [y/N]: "
        ).strip().casefold()
        sample_seconds = 10 if sample_answer in {"y", "yes"} else 0
    elif not 0 <= sample_seconds <= 30:
        output.print("[red]--sample-seconds must be between 0 and 30.[/red]", file=sys.stderr)
        return 1

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        before = {
            path.resolve()
            for path in output_dir.glob("assessment_*.json")
        }
    except OSError as error:
        output.print(f"[red]Could not access the reports directory:[/red] {error}", file=sys.stderr)
        return 1

    phase(output, 1, 2, "Local assessment", "Answer a few short questions; no data is sent yet.")
    collector_command = [
        sys.executable,
        str(CLIENT_DIR / "collector.py"),
        "--output-dir",
        str(output_dir),
    ]
    if no_color:
        collector_command.append("--no-color")
    collector_command.append("--no-header")
    if verbose:
        collector_command.append("--verbose")
    if sample_seconds:
        collector_command.extend(["--sample-seconds", str(sample_seconds)])
    collection_status = _run(collector_command, "Collecting and scoring this PC")
    if collection_status != 0:
        return collection_status

    try:
        report_path = _created_assessment(before, output_dir)
    except (OSError, RuntimeError) as error:
        output.print(f"[red]{error}[/red]", file=sys.stderr)
        return 1

    phase(output, 2, 2, "Optional catalog lookup", "Review local results before any online lookup or upload.")
    comparison_command = [
        sys.executable,
        str(CLIENT_DIR / "compare_and_submit.py"),
        "--report",
        str(report_path),
        "--components",
        *COMPONENTS,
        "--upload",
    ]
    if no_color:
        comparison_command.append("--no-color")
    if verbose:
        comparison_command.append("--verbose")
    comparison_status = _run(
        comparison_command,
        "Finding closest passing specifications and preparing backend submission",
    )
    if comparison_status != 0:
        output.print(
            "[yellow]Local assessment retained.[/yellow] Catalog lookup or upload did not complete."
        )
        return comparison_status

    try:
        _remove_intermediate_report(report_path)
    except RuntimeError as error:
        output.print(f"[red]{error}[/red]", file=sys.stderr)
        return 1

    output.print(f"\n[green]Done.[/green] Local reports: {output_dir.resolve()}")
    output.print("[dim]Any upload was made only after explicit consent.[/dim]")
    return 0


def main() -> int:
    return run_workflow()


if __name__ == "__main__":
    raise SystemExit(main())
