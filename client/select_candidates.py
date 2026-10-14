"""Select up to two upgrade options for a saved client report."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from candidate_engine import CATALOG_DIRS, select_candidates


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Select up to two closest passing options from a local BuildCores OpenDB snapshot."
    )
    parser.add_argument("--report", required=True, type=Path, help="Saved collector assessment JSON.")
    parser.add_argument("--catalog-root", required=True, type=Path, help="Folder containing CPU/GPU/RAM/Storage/Motherboard.")
    parser.add_argument("--component", required=True, choices=sorted(CATALOG_DIRS))
    parser.add_argument("--limit", type=int, default=2, help="Maximum options (1-2).")
    parser.add_argument("--output", type=Path, help="Output recommendations JSON (default: alongside input report).")
    args = parser.parse_args()

    try:
        source_bytes = args.report.read_bytes()
        report = json.loads(source_bytes.decode("utf-8"))
        if not isinstance(report, dict):
            raise ValueError("Assessment report must be a JSON object.")
        recommendations = select_candidates(
            report,
            args.catalog_root,
            args.component,
            args.limit,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))

    recommendations["source_report_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    output = args.output or args.report.with_name(
        f"{args.report.stem}_{args.component}_candidates.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(recommendations, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Candidate selection status: {recommendations['status']}")
    print(f"Candidates returned: {len(recommendations['candidates'])}")
    print(f"Recommendations: {output.resolve()}")
    if recommendations["candidates"]:
        print("Candidates are ordered by closest passing relative specifications.")
        print("Current price and affordability are unavailable in the catalog.")
        print("Compatibility remains unknown unless separately verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
