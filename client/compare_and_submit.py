"""Attach selected candidates to a saved assessment and upload with consent."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

from api_client import upload_report
from catalog_client import (
    DEFAULT_API_BASE_URL,
    select_remote_candidates,
)
from candidate_engine import CATALOG_DIRS, select_candidates
from collector import _render


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{path} is not valid UTF-8 JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return value, raw


def _consent() -> bool:
    print(
        "\nUPLOAD CONSENT\n"
        "The backend will receive your questionnaire answers, detected "
        "hardware, assessment, and the two highest-gap component shortlists.\n"
        "No upload occurs unless you explicitly agree."
    )
    answer = input("Submit this combined report to the SysGap backend? [y/N]: ").strip().casefold()
    return answer in {"y", "yes"}


def _select_top_component_gaps(
    report: dict[str, Any],
    recommendation_files: list[dict[str, Any]],
    limit: int = 2,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Rank candidate-bearing components by profile-fit shortfall, largest first."""
    scores = (
        ((report.get("assessment") or {}).get("profile_comparison") or {}).get(
            "component_scores"
        )
        or {}
    )
    ranked = []
    for order, recommendation in enumerate(recommendation_files):
        component = recommendation.get("component")
        score_record = scores.get(component)
        score = score_record.get("score") if isinstance(score_record, dict) else None
        candidates = recommendation.get("candidates")
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
            or score >= 100
            or not isinstance(candidates, list)
            or not candidates
        ):
            continue
        gap = round(100 - score, 1)
        ranked.append((gap, order, recommendation, float(score)))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected = [
        {
            "component": recommendation["component"],
            "profile_fit_score": score,
            "profile_floor_gap": gap,
            "candidate_count": len(recommendation["candidates"]),
        }
        for gap, _, recommendation, score in ranked[:limit]
    ]
    selected_components = {item["component"] for item in selected}
    selected_recommendations = [
        recommendation for _, _, recommendation, _ in ranked[:limit]
        if recommendation["component"] in selected_components
    ]
    return selected_recommendations, selected


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Query the SysGap catalog, combine candidates with an assessment, and optionally upload."
    )
    parser.add_argument("--report", required=True, type=Path)
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--recommendations",
        type=Path,
        nargs="+",
        help="Previously generated candidate JSON files.",
    )
    source.add_argument(
        "--catalog-root",
        type=Path,
        help="OpenDB catalog folder; selects candidates directly without intermediate files.",
    )
    parser.add_argument(
        "--components",
        nargs="+",
        choices=sorted(CATALOG_DIRS),
        help="Components to query (default: all supported categories).",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("SYSGAP_API_BASE_URL", DEFAULT_API_BASE_URL),
        help="SysGap API base URL; defaults to the deployed service or SYSGAP_API_BASE_URL.",
    )
    parser.add_argument("--limit", type=int, default=2, help="Maximum upgrade options per component (1-2).")
    parser.add_argument("--upload", action="store_true", help="Ask consent and upload after saving the merged report.")
    args = parser.parse_args()

    try:
        if not 1 <= args.limit <= 2:
            raise ValueError("--limit must be between 1 and 2.")
        report, report_bytes = _read_json(args.report)
        selected_components = args.components or [
            "cpu",
            "gpu",
            "ram",
            "storage",
            "motherboard",
        ]
        if args.recommendations:
            if args.components is not None:
                raise ValueError("--components cannot be used with --recommendations.")
            recommendation_files = [_read_json(path)[0] for path in args.recommendations]
        else:
            recommendation_files = []
            for component in selected_components:
                print(
                    f"Checking {component.upper()} score and requirement gap..."
                )
                if args.catalog_root:
                    result = select_candidates(
                        report, args.catalog_root, component, args.limit
                    )
                else:
                    result = select_remote_candidates(
                        report, component, args.api_url, args.limit
                    )
                recommendation_files.append(result)

        actual_hash = hashlib.sha256(report_bytes).hexdigest()
        for recommendations in recommendation_files:
            if recommendations.get("schema_version") != 1:
                raise ValueError("Unsupported candidate selection schema version.")
            source_hash = recommendations.get("source_report_sha256")
            if source_hash is not None and source_hash != actual_hash:
                raise ValueError("Candidate file was generated from a different report; re-run selection.")
            if not isinstance(recommendations.get("component"), str) or not isinstance(
                recommendations.get("candidates"), list
            ):
                raise ValueError("Candidate file is missing its component or candidate list.")
            if source_hash is None:
                recommendations["source_report_sha256"] = actual_hash
        components = [item.get("component") for item in recommendation_files]
        if len(set(components)) != len(components):
            raise ValueError("Provide at most one candidate file per component.")
    except (OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))

    selected_recommendations, selected_component_gaps = _select_top_component_gaps(
        report,
        recommendation_files,
    )
    selected_names = {item["component"] for item in selected_recommendations}
    report["recommendation_selection"] = {
        "method": "largest profile-fit gap (100 minus component fit score); tied gaps preserve the requested component order",
        "maximum_component_categories": 2,
        "selected_components": selected_component_gaps,
        "not_selected_components": [
            item["component"]
            for item in recommendation_files
            if item["component"] not in selected_names
        ],
    }

    existing = report.get("recommendations") or []
    if not isinstance(existing, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("component"), str)
        for item in existing
    ):
        print("Existing report recommendations must be a list of component objects.", file=sys.stderr)
        return 1
    new_by_component = {item["component"]: item for item in recommendation_files}
    all_recommendations = [
        item for item in existing
        if not isinstance(item, dict) or item.get("component") not in new_by_component
    ] + recommendation_files
    report["catalog_lookup_results"] = all_recommendations
    report["recommendations"] = selected_recommendations
    report["generated_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    output_json = args.report.with_name(f"{args.report.stem}_with_recommendations.json")
    output_text = output_json.with_suffix(".txt")
    try:
        output_json.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        output_text.write_text(_render(report), encoding="utf-8")
    except OSError as error:
        print(f"Could not write merged report: {error}", file=sys.stderr)
        return 1

    print(f"Combined JSON report: {output_json.resolve()}")
    print(f"Combined readable report: {output_text.resolve()}")
    print("\nTop component gaps selected for backend:")
    if selected_component_gaps:
        for item in selected_component_gaps:
            print(
                f"  {item['component'].upper()}: score "
                f"{item['profile_fit_score']:.1f}/100; "
                f"{item['profile_floor_gap']:.1f}-point gap; "
                f"{item['candidate_count']} candidate(s)"
            )
    else:
        print("  None: no known below-floor component had passing catalog candidates.")
    print("\nAll per-component catalog lookups (retained in the local report):")
    for item in report["recommendations"]:
        print(
            f"{item['component']}: {item['status']} "
            f"({len(item['candidates'])} candidates)"
        )

    if args.upload:
        print(
            "Warning: the currently deployed report endpoint runs a legacy gaming "
            "utilization rule. Inventory-only reports contain no workload utilization, "
            "so its stored diagnosis may be misleading; no utilization values will be invented."
        )
        if not _consent():
            print("Upload cancelled; local reports were retained.")
            return 0
        try:
            report_endpoint = f"{args.api_url.rstrip('/')}/api/v1/reports"
            backend_report = copy.deepcopy(report)
            backend_report["recommendations"] = selected_recommendations
            backend_report.pop("catalog_lookup_results", None)
            response = upload_report(report_endpoint, backend_report)
        except (RuntimeError, ValueError) as error:
            print(f"Report upload failed: {error}", file=sys.stderr)
            return 2
        print("Combined report uploaded successfully to the SysGap backend.")
        report_url = response.get("report_url")
        if isinstance(report_url, str):
            print(f"Report URL: {report_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
