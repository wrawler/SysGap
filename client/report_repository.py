"""Local report persistence shared by collection and comparison workflows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


ReportRenderer = Callable[[dict[str, Any]], str]


def write_report(
    report: dict[str, Any],
    output_dir: Path,
    render: ReportRenderer,
    *,
    stem: str | None = None,
) -> tuple[Path, Path]:
    """Write one report atomically enough for a local CLI workflow."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report_stem = stem or f"assessment_{report['report_id']}"
    json_path = output_dir / f"{report_stem}.json"
    text_path = output_dir / f"{report_stem}.txt"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    text_path.write_text(render(report), encoding="utf-8")
    return json_path, text_path
