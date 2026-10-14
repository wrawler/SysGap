"""Transparent v1 resource-floor profiles for use-case fallback comparisons."""

from __future__ import annotations

from typing import Any

PROFILE_REQUIREMENT_KEYS = (
    "min_ram_gib",
    "min_vram_gib",
    "min_cpu_cores",
    "min_cpu_base_clock_ghz",
    "min_free_storage_gib",
)

PROFILE_SCORING_FEATURES = {
    "cpu": {
        "metric": "cpu_physical_cores",
        "inventory_field": "physical_cores",
        "label": "Detected physical CPU cores",
        "limits": "Does not measure instructions per clock, sustained frequency, thermal throttling, or application performance.",
    },
    "gpu": {
        "metric": "dedicated_vram",
        "inventory_field": "dedicated_memory_gib",
        "label": "Selected workload GPU dedicated VRAM",
        "limits": "Does not measure GPU compute/rasterization speed; requires one selected adapter and a valid dedicated-VRAM reading.",
    },
    "ram": {
        "metric": "ram_capacity",
        "inventory_field": "total_gib",
        "label": "Installed RAM capacity",
        "limits": "Does not measure memory bandwidth, latency, channel configuration, or workload memory pressure.",
    },
    "storage": {
        "metric": "free_workspace",
        "inventory_field": "free_gib_at_scan",
        "label": "Best-case free workspace on one volume",
        "limits": "Does not measure read/write throughput or latency; target volume and catalog drive fit are unknown.",
    },
}

PROFILES: dict[str, dict[str, Any]] = {
    "general": {
        "label": "General use baseline",
        "description": "Everyday productivity and multitasking; no graphics-heavy workload target.",
        "assumptions": ["Does not represent a specific application or performance target."],
        "scoring_features": PROFILE_SCORING_FEATURES,
        "requirements": {
            "min_ram_gib": 16,
            "min_vram_gib": None,
            "min_cpu_cores": 4,
            "min_cpu_base_clock_ghz": None,
            "min_free_storage_gib": 30,
        },
    },
    "gaming": {
        "label": "Gaming baseline",
        "description": "General 1080p gaming planning baseline; no specific game, quality setting, or FPS target.",
        "assumptions": [
            "Resolution and target FPS can materially change requirements; this baseline does not predict frame rate."
        ],
        "scoring_features": PROFILE_SCORING_FEATURES,
        "requirements": {
            "min_ram_gib": 16,
            "min_vram_gib": 8,
            "min_cpu_cores": 6,
            "min_cpu_base_clock_ghz": None,
            "min_free_storage_gib": 100,
        },
    },
    "video_editing": {
        "label": "Video editing baseline",
        "description": "General 4K editing and project-workspace planning baseline.",
        "assumptions": [
            "Codec, effects, timeline complexity, application, and proxy workflow change actual requirements."
        ],
        "scoring_features": PROFILE_SCORING_FEATURES,
        "requirements": {
            "min_ram_gib": 32,
            "min_vram_gib": 8,
            "min_cpu_cores": 8,
            "min_cpu_base_clock_ghz": None,
            "min_free_storage_gib": 200,
        },
    },
    "rendering": {
        "label": "Rendering baseline",
        "description": "General CPU/GPU rendering and project-workspace planning baseline.",
        "assumptions": [
            "Renderer, scene complexity, render engine, and CPU-versus-GPU mode change actual requirements."
        ],
        "scoring_features": PROFILE_SCORING_FEATURES,
        "requirements": {
            "min_ram_gib": 32,
            "min_vram_gib": 8,
            "min_cpu_cores": 8,
            "min_cpu_base_clock_ghz": None,
            "min_free_storage_gib": 200,
        },
    },
    "local_ai": {
        "label": "Local AI baseline",
        "description": "Small quantized local-model experimentation planning baseline.",
        "assumptions": [
            "Model architecture, parameter count, quantization, context length, and inference engine strongly affect RAM and VRAM needs."
        ],
        "scoring_features": PROFILE_SCORING_FEATURES,
        "requirements": {
            "min_ram_gib": 32,
            "min_vram_gib": 12,
            "min_cpu_cores": 6,
            "min_cpu_base_clock_ghz": None,
            "min_free_storage_gib": 100,
        },
    },
}

METRIC_DEFINITIONS = {
    "min_ram_gib": ("ram_capacity", "Installed RAM", "GiB"),
    "min_vram_gib": ("dedicated_vram", "Selected workload GPU dedicated VRAM", "GiB"),
    "min_cpu_cores": ("cpu_physical_cores", "Physical CPU cores", "cores"),
    "min_cpu_base_clock_ghz": (
        "cpu_base_clock",
        "CPU performance-core base clock",
        "GHz",
    ),
    "min_free_storage_gib": (
        "free_workspace",
        "Best-case free space on one detected volume",
        "GiB",
    ),
}


def resolve_requirements(questionnaire: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Use user-entered values first, then fill blanks from a declared profile."""
    supplied = questionnaire.get("user_supplied_requirements") or {}
    if not isinstance(supplied, dict):
        raise ValueError("Assessment requirements must be an object.")
    purpose = questionnaire.get("purpose")
    profile = PROFILES.get(purpose)
    effective: dict[str, Any] = dict(supplied)
    sources: dict[str, str] = {}
    for key in PROFILE_REQUIREMENT_KEYS:
        value = supplied.get(key)
        if value is not None:
            effective[key] = value
            sources[key] = "user_supplied"
        elif profile is not None and profile["requirements"].get(key) is not None:
            effective[key] = profile["requirements"][key]
            sources[key] = "purpose_profile"
        else:
            effective[key] = None
            sources[key] = "not_set"
    return effective, sources
