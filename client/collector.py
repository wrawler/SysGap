"""Questionnaire, Windows hardware inventory, assessment, and optional upload."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from api_client import upload_report
from config import ClientConfig
from decision_engine import evaluate_assessment
from hardware_inventory import collect_inventory
from passive_sample import collect_passive_sample
from questionnaire import run_questionnaire
from report_repository import write_report

SCHEMA_VERSION = 1
CLIENT_VERSION = "0.2.0"


def _render(report: dict[str, Any]) -> str:
    assessment = report["assessment"]
    hardware = report["hardware"]
    cpu = hardware.get("cpu") or {}
    computer = hardware.get("computer") or {}
    memory = hardware.get("memory") or {}
    storage = hardware.get("storage") or {}
    lines = [
        "SYSGAP HARDWARE SUITABILITY ASSESSMENT",
        "=" * 42,
        f"Generated (UTC): {report['generated_at_utc']}",
        f"Purpose: {report['questionnaire']['purpose_label']}",
        f"Activity: {report['questionnaire'].get('activity') or 'Not specified'}",
        f"Reported symptom: {report['questionnaire']['symptom_label']}",
        f"Overall: {assessment['overall_status']}",
        "",
        assessment["summary"],
        "",
        "DETECTED HARDWARE",
        "-----------------",
        f"System: {computer.get('manufacturer') or 'Unknown'} {computer.get('model') or 'Unknown'}",
        f"OS: {hardware['operating_system']['name']} {hardware['operating_system']['release']} "
        f"({hardware['operating_system']['architecture']})",
        f"CPU: {cpu.get('name') or 'Not available'}; "
        f"{cpu.get('physical_cores') or 'unknown'} cores / "
        f"{cpu.get('logical_processors') or 'unknown'} logical processors",
    ]
    if hardware.get("gpus"):
        lines.append("Graphics:")
        for gpu in hardware["gpus"]:
            vram = gpu.get("dedicated_memory_gib")
            vram_text = f"{vram:g} GiB dedicated" if isinstance(vram, (int, float)) else "dedicated memory unavailable"
            lines.append(f"- {gpu.get('name') or 'Unknown GPU'} ({vram_text})")
    else:
        lines.append("Graphics: Not available")

    memory_summary = memory.get("summary") or {}
    lines.append(
        f"RAM: {memory_summary.get('total_gib') if memory_summary.get('total_gib') is not None else 'Not available'} GiB total"
    )
    for module in memory.get("modules") or []:
        lines.append(
            f"- Module: {module.get('capacity_gib', 'unknown')} GiB, "
            f"{module.get('speed_mhz', 'unknown')} MHz, "
            f"{module.get('manufacturer') or 'manufacturer unknown'} "
            f"{module.get('part_number') or ''}".rstrip()
        )
    disks = storage.get("physical_disks") or []
    if disks:
        lines.append("Physical storage:")
        for disk in disks:
            lines.append(
                f"- {disk.get('model') or 'Unknown disk'}; "
                f"{disk.get('capacity_gib') if disk.get('capacity_gib') is not None else 'unknown'} GiB; "
                f"{disk.get('media_type') or 'type unknown'}"
            )
    else:
        lines.append("Physical storage: Not available")
    for volume in storage.get("volumes") or []:
        free = volume.get("free_gib_at_scan")
        lines.append(
            f"- Volume {volume.get('mountpoint') or '?'}: "
            f"{free if free is not None else 'unknown'} GiB free at scan"
        )

    motherboard = hardware.get("motherboard") or {}
    bios = hardware.get("bios") or {}
    lines.extend([
        f"Motherboard: {motherboard.get('manufacturer') or 'Unknown'} "
        f"{motherboard.get('product') or ''}".rstrip(),
        f"BIOS: {bios.get('version') or 'Not available'}",
        "",
        "FINDINGS",
        "--------",
    ])
    for finding in assessment["findings"]:
        lines.extend([
            f"[{finding['status'].upper()}] {finding['title']} ({finding['area']})",
            f"  Confidence: {finding['confidence']}",
            *[f"  Evidence: {item}" for item in finding["evidence"]],
            *[f"  Caveat: {item}" for item in finding["caveats"]],
            f"  Next step: {finding['next_step']}",
            "",
        ])
    profile_comparison = assessment.get("profile_comparison") or {}
    if profile_comparison.get("profile_label") or profile_comparison.get("metrics"):
        lines.extend([
            "PROFILE / REQUIREMENT FLOOR COMPARISON",
            "--------------------------------------",
            f"Profile: {profile_comparison.get('profile_label') or 'User-entered requirements'}",
            profile_comparison.get("description") or "",
            "Attainment is observed capacity divided by that metric's floor, capped at 100%; it is not a performance score or bottleneck diagnosis.",
        ])
        for metric in profile_comparison.get("metrics", []):
            observed = metric.get("observed")
            target = metric.get("target")
            source = (
                "profile default"
                if metric.get("requirement_source") == "purpose_profile"
                else "user supplied"
            )
            if observed is None:
                detail = "comparison unknown"
            else:
                detail = f"{metric['target_attainment_percent']:.1f}% of floor"
            observed_text = (
                f"{observed:g} {metric['unit']}" if isinstance(observed, (int, float))
                else "not detected"
            )
            lines.append(
                f"- {metric['label']}: {detail}; detected {observed_text}; "
                f"target {target:g} {metric['unit']} ({source}; {metric['status']})"
            )
        for component, score in (profile_comparison.get("component_scores") or {}).items():
            score_text = (
                f"{score['score']:.1f}/100"
                if isinstance(score.get("score"), (int, float))
                else "unknown"
            )
            lines.append(
                f"  {component.upper()} profile-fit score: {score_text} "
                f"({score['status']}; based on {score['basis']})"
            )
            lines.append(f"    Score limitation: {score['limits']}")
        lines.extend(
            f"- Profile assumption: {item}"
            for item in profile_comparison.get("assumptions", [])
        )
        lines.append("")
    lines.extend([
        "LIMITATIONS",
        "-----------",
        *[f"- {item}" for item in assessment["assumptions"]],
    ])
    if assessment.get("requirement_source_reference"):
        lines.append(f"Requirement source supplied by user: {assessment['requirement_source_reference']}")
    sample = report.get("ambient_sample")
    if sample:
        lines.extend([
            "",
            "OPTIONAL PASSIVE SAMPLE",
            "-----------------------",
            f"Duration: {sample['duration_seconds']} seconds",
            f"Interpretation: {sample['interpretation']}",
            f"CPU summary: {json.dumps(sample['cpu'], ensure_ascii=False)}",
            f"Memory summary: {json.dumps(sample['memory'], ensure_ascii=False)}",
            f"Disk I/O rates: {json.dumps(sample['disk_io'], ensure_ascii=False)}",
            f"NVIDIA GPU readings: {json.dumps(sample['nvidia_gpus'], ensure_ascii=False)}",
        ])
        lines.extend(f"- {item}" for item in sample["collection_notes"])
    if assessment["collection_notes"]:
        lines.extend(["", "COLLECTION NOTES", "----------------"])
        lines.extend(f"- {item}" for item in assessment["collection_notes"])
    selection = report.get("recommendation_selection") or {}
    if selection:
        lines.extend([
            "",
            "TOP COMPONENT GAPS SELECTED FOR BACKEND",
            "----------------------------------------",
            "Ranked by profile-fit shortfall (100 minus score); at most two component categories are selected.",
        ])
        selected_components = selection.get("selected_components") or []
        if selected_components:
            lines.extend(
                f"- {item['component'].upper()}: score "
                f"{item['profile_fit_score']:.1f}/100; "
                f"gap {item['profile_floor_gap']:.1f} points; "
                f"{item['candidate_count']} candidate(s)"
                for item in selected_components
            )
        else:
            lines.append("- None: no known below-floor component had passing catalog candidates.")
    recommendations = report.get("recommendations") or []
    if recommendations:
        lines.extend(["", "CANDIDATE SHORTLISTS", "--------------------"])
        for shortlist in recommendations:
            lines.extend([
                f"{shortlist['component'].upper()}: {shortlist['status']}",
                f"  Ranking: {shortlist.get('ranking_method', 'not ranked')}",
            ])
            installed_comparison = shortlist.get("installed_comparison")
            if isinstance(installed_comparison, dict):
                installed_value = installed_comparison.get("installed_value_gib")
                required_value = installed_comparison.get("required_value_gib")
                comparison_text = (
                    f"  Installed comparison: {installed_comparison.get('status', 'unknown')}"
                )
                if isinstance(installed_value, (int, float)):
                    comparison_text += f"; detected {installed_value:g} GiB"
                if isinstance(required_value, (int, float)):
                    comparison_text += f"; supplied floor {required_value:g} GiB"
                lines.append(comparison_text)
            query = shortlist.get("query")
            if isinstance(query, dict):
                lines.append(
                    f"  Query criteria: {json.dumps(query.get('filters', []), ensure_ascii=False)}"
                )
            for candidate in shortlist.get("candidates", []):
                capacity = candidate.get("capacity_value_gib")
                capacity_text = f"; capacity {capacity:g} GiB" if isinstance(capacity, (int, float)) else ""
                lines.append(
                    f"  - {candidate.get('manufacturer') or ''} {candidate.get('model') or 'Unknown model'}"
                    f"{capacity_text}; compatibility {candidate.get('compatibility_status', 'unknown')}"
                )
                if candidate.get("why_shown"):
                    lines.append(f"    Why shown: {candidate['why_shown']}")
                lines.append(f"    Specs: {json.dumps(candidate.get('details') or {}, ensure_ascii=False)}")
                lines.append(
                    "    Price/value: unavailable; candidate ordering uses closest passing specifications only."
                )
                lines.append(f"    OpenDB ID: {candidate.get('candidate_id')}")
                if candidate.get("manufacturer_source_url"):
                    lines.append(f"    Manufacturer specs: {candidate['manufacturer_source_url']}")
                lines.extend(f"    Note: {note}" for note in candidate.get("notes", []))
            lines.extend(f"  Note: {note}" for note in shortlist.get("notes", []))
    lines.append("")
    return "\n".join(lines)


def _write_reports(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    return write_report(report, output_dir, _render)


def _ask_upload() -> bool:
    print(
        "\nUpload is optional. The server will receive the hardware inventory, "
        "questionnaire answers, and assessment. Review the local report first."
    )
    return input("Upload this report to the configured API? [y/N]: ").strip().lower() in {"y", "yes"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a hardware suitability assessment without a benchmark or stress test."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "reports",
        help="Directory for local JSON/text reports.",
    )
    parser.add_argument(
        "--api-url",
        default=ClientConfig.from_environment().report_api_url,
        help="Full HTTPS report endpoint; alternatively set SYSGAP_REPORT_API_URL.",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Ask for consent to upload the report (requires --api-url or environment variable).",
    )
    parser.add_argument(
        "--sample-seconds",
        type=int,
        default=0,
        help="Optionally observe current CPU/RAM/disk/GPU activity for 1-30 seconds; 0 disables it.",
    )
    args = parser.parse_args()

    if not 0 <= args.sample_seconds <= 30:
        parser.error("--sample-seconds must be 0 (disabled) or between 1 and 30.")
    if args.upload and not args.api_url:
        parser.error("--upload requires --api-url or SYSGAP_REPORT_API_URL.")

    questionnaire = run_questionnaire()
    print("\nCollecting a one-time hardware inventory...")
    hardware, notes = collect_inventory()
    ambient_sample = None
    if args.sample_seconds:
        print(f"Sampling current ambient activity for up to {args.sample_seconds} seconds...")
        try:
            ambient_sample = collect_passive_sample(args.sample_seconds)
        except (ValueError, OSError) as error:
            print(f"Passive sample failed: {error}", file=sys.stderr)
            return 4
    assessment = evaluate_assessment(questionnaire, hardware, notes)
    if ambient_sample is not None:
        assessment["assumptions"].append(
            "An optional passive sample reflects only activity during its short collection window."
        )
    report = {
        "schema_version": SCHEMA_VERSION,
        "client_version": CLIENT_VERSION,
        "report_id": uuid.uuid4().hex,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "questionnaire": questionnaire,
        "hardware": hardware,
        "ambient_sample": ambient_sample,
        "assessment": assessment,
    }

    try:
        json_path, text_path = _write_reports(report, args.output_dir)
    except OSError as error:
        print(f"Could not write local report: {error}", file=sys.stderr)
        return 1

    print("\nAssessment complete.")
    print(f"JSON report: {json_path.resolve()}")
    print(f"Readable report: {text_path.resolve()}")
    print(f"Overall status: {assessment['overall_status']}")
    print("No benchmark or stress test was run.")

    if args.upload:
        if _ask_upload():
            try:
                response = upload_report(args.api_url, report)
            except (RuntimeError, ValueError) as error:
                print(f"Report upload failed: {error}", file=sys.stderr)
                return 3
            report_url = response.get("report_url")
            print("Report uploaded successfully.")
            if isinstance(report_url, str):
                print(f"Report URL: {report_url}")
            else:
                print("API response did not include a report_url.")
        else:
            print("Upload cancelled; local reports were retained.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
