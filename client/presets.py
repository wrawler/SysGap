"""Curated, offline workload presets used by the client questionnaire.

These are planning heuristics, not vendor requirements or performance
guarantees. Keep the values explicit and versioned so report interpretation is
reproducible.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

PRESET_DATA_VERSION = "1"

PRESETS: dict[str, tuple[dict[str, Any], ...]] = {
    "gaming": (
        {
            "id": "gaming_1080p_competitive",
            "label": "1080p · competitive / balanced",
            "description": "1080p play with a balanced or competitive quality target.",
            "requirements": {
                "min_ram_gib": 16,
                "min_vram_gib": 6,
                "min_cpu_cores": 6,
                "min_free_storage_gib": 100,
            },
            "assumptions": ["Actual FPS depends on the game, settings, and engine."],
        },
        {
            "id": "gaming_1440p_high",
            "label": "1440p · high quality",
            "description": "1440p play targeting high visual quality.",
            "requirements": {
                "min_ram_gib": 16,
                "min_vram_gib": 8,
                "min_cpu_cores": 6,
                "min_free_storage_gib": 150,
            },
            "assumptions": ["Ray tracing, texture packs, and target FPS can raise requirements."],
        },
        {
            "id": "gaming_4k_high",
            "label": "4K · high quality",
            "description": "4K play targeting high visual quality.",
            "requirements": {
                "min_ram_gib": 32,
                "min_vram_gib": 12,
                "min_cpu_cores": 8,
                "min_free_storage_gib": 200,
            },
            "assumptions": ["Upscaling, ray tracing, and game-specific optimization materially affect results."],
        },
    ),
    "video_editing": (
        {
            "id": "video_1080p_basic",
            "label": "1080p · cuts and light effects",
            "description": "1080p editing with cuts, transitions, and light effects.",
            "requirements": {
                "min_ram_gib": 16,
                "min_vram_gib": 4,
                "min_cpu_cores": 6,
                "min_free_storage_gib": 150,
            },
            "assumptions": ["Codec, effects, proxies, and timeline length can change requirements."],
        },
        {
            "id": "video_4k_standard",
            "label": "4K · standard editing",
            "description": "4K editing with ordinary effects and a practical project workspace.",
            "requirements": {
                "min_ram_gib": 32,
                "min_vram_gib": 8,
                "min_cpu_cores": 8,
                "min_free_storage_gib": 300,
            },
            "assumptions": ["Proxy media may reduce active playback requirements."],
        },
        {
            "id": "video_4k_effects",
            "label": "4K · effects-heavy",
            "description": "4K editing with layered effects, grading, or compositing.",
            "requirements": {
                "min_ram_gib": 64,
                "min_vram_gib": 12,
                "min_cpu_cores": 10,
                "min_free_storage_gib": 500,
            },
            "assumptions": ["The selected editor, effects, codecs, and proxy workflow remain decisive."],
        },
    ),
    "local_ai": (
        {
            "id": "ai_7b_q4",
            "label": "Up to 7B parameters · 4-bit quantized",
            "description": "Small local model experimentation using 4-bit quantization.",
            "parameters_billion": 7,
            "quantization": "4-bit",
            "requirements": {
                "min_ram_gib": 16,
                "min_vram_gib": 8,
                "min_cpu_cores": 6,
                "min_free_storage_gib": 30,
            },
            "assumptions": ["Context length and runtime overhead can require more memory."],
        },
        {
            "id": "ai_13b_q4",
            "label": "Up to 13B parameters · 4-bit quantized",
            "description": "Medium local model experimentation using 4-bit quantization.",
            "parameters_billion": 13,
            "quantization": "4-bit",
            "requirements": {
                "min_ram_gib": 32,
                "min_vram_gib": 12,
                "min_cpu_cores": 8,
                "min_free_storage_gib": 60,
            },
            "assumptions": ["Long contexts, larger batches, and runtime overhead can require more memory."],
        },
        {
            "id": "ai_30b_q4",
            "label": "Up to 30B parameters · 4-bit quantized",
            "description": "Large local model experimentation using 4-bit quantization.",
            "parameters_billion": 30,
            "quantization": "4-bit",
            "requirements": {
                "min_ram_gib": 64,
                "min_vram_gib": 24,
                "min_cpu_cores": 10,
                "min_free_storage_gib": 120,
            },
            "assumptions": ["Full GPU residency may not be possible; CPU offload changes performance substantially."],
        },
    ),
}


def available_presets(purpose: str) -> tuple[dict[str, Any], ...]:
    """Return immutable-by-convention copies for one supported purpose."""
    return tuple(deepcopy(item) for item in PRESETS.get(purpose, ()))


def get_preset(purpose: str, preset_id: str) -> dict[str, Any]:
    for preset in PRESETS.get(purpose, ()):
        if preset["id"] == preset_id:
            return deepcopy(preset)
    raise ValueError(f"Unknown {purpose} preset: {preset_id}")
