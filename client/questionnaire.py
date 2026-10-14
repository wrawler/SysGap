"""Purpose and symptom questionnaire; no diagnosis is inferred from answers alone."""

from __future__ import annotations

import math
from typing import Any, Callable

from profiles import PROFILES, resolve_requirements
from presets import available_presets, get_preset, PRESET_DATA_VERSION

PURPOSES = {
    "gaming": "Gaming",
    "video_editing": "Video editing",
    "rendering": "3D / CPU-GPU rendering",
    "local_ai": "Local AI / machine learning",
    "general": "Everyday / general use",
    "upgrade_planning": "Upgrade planning",
    "other": "Other",
}

SYMPTOMS = {
    "none": "No current problem; checking suitability or planning an upgrade",
    "slow_or_low_fps": "Low frame rate or generally slow performance",
    "stutter": "Stuttering, pauses, or freezing",
    "long_render": "Long export, render, or computation time",
    "memory_warning": "Memory/VRAM warning or out-of-memory error",
    "slow_loading": "Slow application/game loading or file transfers",
    "crash_or_shutdown": "Crash, restart, or unexpected shutdown",
    "other": "Other / not sure",
}


def _choose(prompt: str, options: dict[str, str], input_fn: Callable[[str], str]) -> str:
    keys = list(options)
    print(f"\n{prompt}")
    for index, key in enumerate(keys, start=1):
        print(f"  {index}. {options[key]}")
    while True:
        answer = input_fn("Select a number: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(keys):
            return keys[int(answer) - 1]
        print(f"Enter a number from 1 to {len(keys)}.")


def _optional_text(prompt: str, input_fn: Callable[[str], str]) -> str | None:
    value = input_fn(prompt).strip()
    return value or None


def _optional_positive_number(
    prompt: str,
    input_fn: Callable[[str], str],
) -> float | None:
    while True:
        value = input_fn(prompt).strip()
        if not value:
            return None
        try:
            number = float(value)
        except ValueError:
            print("Enter a positive number or leave blank if unknown.")
            continue
        if math.isfinite(number) and number > 0:
            return number
        print("Enter a positive number or leave blank if unknown.")


def _optional_positive_integer(
    prompt: str,
    input_fn: Callable[[str], str],
) -> int | None:
    while True:
        value = input_fn(prompt).strip()
        if not value:
            return None
        if value.isdigit() and int(value) > 0:
            return int(value)
        print("Enter a positive whole number or leave blank if unknown.")


def run_questionnaire(
    input_fn: Callable[[str], str] = input,
    *,
    verbose: bool = False,
) -> dict[str, Any]:
    purpose = _choose("What do you mainly want to use this PC for?", PURPOSES, input_fn)
    symptom = _choose("Which best describes your current situation?", SYMPTOMS, input_fn)

    context: dict[str, Any] = {}
    preset = None
    if purpose in {"gaming", "video_editing", "local_ai"}:
        options = {
            item["id"]: item["label"] for item in available_presets(purpose)
        }
        preset_id = _choose(
            {
                "gaming": "Choose the gaming target:",
                "video_editing": "Choose the editing workload:",
                "local_ai": "Choose the local AI model size:",
            }[purpose],
            options,
            input_fn,
        )
        preset = get_preset(purpose, preset_id)
        context["preset_id"] = preset["id"]
        context["preset_label"] = preset["label"]
        context["preset_description"] = preset["description"]
        if purpose == "local_ai":
            context["parameters_billion"] = preset["parameters_billion"]
            context["quantization"] = preset["quantization"]
            context["context_length_tokens"] = int(
                _choose(
                    "Choose the usual context length:",
                    {
                        "4096": "4k tokens",
                        "8192": "8k tokens",
                        "16384": "16k tokens",
                    },
                    input_fn,
                )
            )
            context["inference_mode"] = _choose(
                "Where should the model mainly run?",
                {
                    "gpu": "GPU-focused",
                    "hybrid": "Hybrid CPU/GPU",
                    "cpu": "CPU-only",
                },
                input_fn,
            )
            context_requirements = dict(preset["requirements"])
            if context["context_length_tokens"] >= 8192:
                context_requirements["min_ram_gib"] += 4
            if context["context_length_tokens"] >= 16384:
                context_requirements["min_ram_gib"] += 4
            if context["inference_mode"] == "cpu":
                context_requirements["min_vram_gib"] = 0
            elif context["context_length_tokens"] >= 8192:
                context_requirements["min_vram_gib"] += 2
            if context["context_length_tokens"] >= 16384 and context["inference_mode"] != "cpu":
                context_requirements["min_vram_gib"] += 2
            preset = {**preset, "requirements": context_requirements}
        if purpose == "gaming":
            context["resolution"] = preset["label"].split("·", 1)[0].strip()
        if purpose == "video_editing":
            context["footage_resolution"] = preset["label"].split("·", 1)[0].strip()
    elif purpose == "rendering":
        context["render_mode"] = _choose(
            "What kind of rendering workload is closest?",
            {
                "cpu": "CPU rendering",
                "gpu": "GPU rendering",
                "mixed": "Mixed CPU/GPU rendering",
            },
            input_fn,
        )

    profile = PROFILES.get(purpose)
    if profile and verbose:
        print(f"\nSelected fallback: {profile['label']}")
        print(profile["description"])
        defaults = profile["requirements"]
        default_text = ", ".join(
            f"{name}={value}"
            for name, value in (
                ("RAM GiB", defaults["min_ram_gib"]),
                ("VRAM GiB", defaults["min_vram_gib"]),
                ("CPU physical cores", defaults["min_cpu_cores"]),
                ("free workspace GiB", defaults["min_free_storage_gib"]),
            )
            if value is not None
        )
        print(f"Planning floors used for blank answers: {default_text}.")

    print(
        "\nIf you have the application's official system requirements, enter the "
        "minimum values here. Your entries override the selected preset or purpose profile. "
        "Blank entries use the selected workload preset first, then its labeled planning baseline; "
        "upgrade_planning/other have no default profile."
    )
    requirements = {
        "min_ram_gib": _optional_positive_number(
            "Minimum RAM required (GiB, optional): ", input_fn
        ),
        "min_vram_gib": _optional_positive_number(
            "Minimum dedicated VRAM required (GiB, optional): ", input_fn
        ),
        "min_cpu_cores": _optional_positive_integer(
            "Minimum CPU physical cores required by the workload (optional): ", input_fn
        ),
        "min_cpu_base_clock_ghz": _optional_positive_number(
            "Minimum CPU performance-core base clock (GHz, optional): ", input_fn
        ),
        "min_free_storage_gib": _optional_positive_number(
            "Minimum free workspace/storage required (GiB, optional): ", input_fn
        ),
        "cpu_requirement_text": _optional_text(
            "CPU requirement as published by the app (text only; optional): ", input_fn
        ),
        "source_reference": _optional_text(
            "Official requirement URL/document reference (optional): ", input_fn
        ),
    }
    response = {
        "purpose": purpose,
        "purpose_label": PURPOSES[purpose],
        "symptom": symptom,
        "symptom_label": SYMPTOMS[symptom],
        "activity": None,
        "context": context,
        "preset_id": preset["id"] if preset else None,
        "preset_data_version": PRESET_DATA_VERSION if preset else None,
        "preset_requirements": preset["requirements"] if preset else {},
        "preset_assumptions": preset["assumptions"] if preset else [],
        "user_supplied_requirements": requirements,
        "answers_are_self_reported": True,
    }
    effective, sources = resolve_requirements(response)
    response["effective_requirements"] = effective
    response["requirement_sources"] = sources
    response["profile_id"] = purpose if purpose in PROFILES else None
    return response
