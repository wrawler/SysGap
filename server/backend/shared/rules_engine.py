"""Small, deterministic diagnosis adapter used by the report API."""

from __future__ import annotations

from typing import Any


def evaluate_gaming_telemetry(telemetry: dict[str, Any]) -> dict[str, Any]:
    utilization = telemetry.get("utilization", {})
    gpu = float(utilization.get("gpu", 0) or 0)
    cpu = float(utilization.get("cpu", 0) or 0)
    if gpu >= 95 and cpu < 80:
        bottleneck = "gpu"
    elif cpu >= 95 and gpu < 80:
        bottleneck = "cpu"
    else:
        bottleneck = "balanced"
    return {"workload": "gaming", "bottleneck": bottleneck, "observed": telemetry}
